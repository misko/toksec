import asyncio
import json
import math
import multiprocessing
import os
import resource
import ssl
import statistics
import time
import zlib
from collections import Counter
from pathlib import Path
from dataclasses import asdict

from toksec.wire import payload, request


BINS = 20002


class ResponseFailure(ValueError):
    """A bounded reason label for an observed HTTP response failure."""


def percentile(histogram, percentile_value):
    count = sum(histogram)
    if not count:
        return None
    target = math.ceil(count * percentile_value)
    total = 0
    for index, value in enumerate(histogram):
        total += value
        if total >= target:
            return index / 10


async def response(reader, expected, zipped):
    raw = await reader.readuntil(b'\r\n\r\n')
    if len(raw) > 65536:
        raise ValueError('oversize response header')
    lines = raw[:-4].split(b'\r\n')
    status = int(lines[0].split(b' ')[1])
    if status != 200:
        raise ResponseFailure(f'http_{status}' if 100 <= status < 600 else 'protocol')
    headers = {}
    for line in lines[1:]:
        name, value = line.split(b':', 1)
        name = name.lower()
        if name in headers and name in (b'content-length', b'transfer-encoding'):
            raise ValueError('ambiguous response framing')
        headers[name] = value.strip().lower()
    if b'transfer-encoding' in headers:
        raise ValueError('unexpected transfer coding')
    length = int(headers[b'content-length'])
    if not 0 <= length <= max(4096, len(expected) + 1024):
        raise ValueError('oversize response body')
    body = await reader.readexactly(length)
    if zipped:
        if headers.get(b'content-encoding') != b'gzip':
            raise ValueError('gzip missing')
        decoder = zlib.decompressobj(31)
        body = decoder.decompress(body, len(expected) + 1)
        if not decoder.eof or decoder.unconsumed_tail:
            raise ValueError('invalid or oversized gzip')
    if body != expected:
        raise ResponseFailure('body_mismatch')
    return headers.get(b'connection') == b'close'


def request_bytes(spec):
    expected = payload(spec['size'], spec['gzip'])
    raw = request(spec['path'], host=spec.get('host', 'alpha.test'), close=not spec['persistent'], headers={'Accept-Encoding': 'gzip'} if spec['gzip'] else {})
    workload_id = spec['id']
    if workload_id.startswith(('gateway-11-', 'gateway-13-')):
        raw = request(spec['path'], close=False, headers={'Authorization': 'Bearer reader'})
    if workload_id.startswith('gateway-16-'):
        raw = request(spec.get('request_path', '/gateway/upload'), method='POST', headers={'Content-Length': str(len(expected))},
                      close=False, body=expected)
    return raw, expected


async def load(spec, clients, start_at):
    histogram = [0] * BINS
    stats = {'attempts': 0, 'successes': 0, 'completed_in_window': 0, 'failures': 0, 'timeouts': 0,
             'payload_bytes': 0, 'peak_inflight': 0, 'clients_started': 0, 'lag_max_ms': 0,
             'lag_samples': 0, 'lag_over_20ms': 0, 'histogram': histogram}
    stats['all_successes'] = 0
    stats['failure_classes'] = Counter()
    active = 0
    raw, expected = request_bytes(spec)
    context = None
    if spec['tls']:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    measurement_start = start_at + spec['warmup_seconds']
    end = measurement_start + spec['seconds']
    cpu_start = time.process_time()

    async def lag_monitor():
        while time.monotonic() < end:
            target = time.monotonic() + 0.01
            await asyncio.sleep(0.01)
            if time.monotonic() >= measurement_start:
                lag = max(0, time.monotonic() - target) * 1000
                stats['lag_max_ms'] = max(stats['lag_max_ms'], lag)
                stats['lag_samples'] += 1
                stats['lag_over_20ms'] += int(lag > 20)

    async def client():
        nonlocal active
        reader = writer = None
        await asyncio.sleep(max(0, start_at - time.monotonic()))
        stats['clients_started'] += 1
        while time.monotonic() < end:
            started = time.monotonic()
            measured = started >= measurement_start
            if measured:
                stats['attempts'] += 1
                active += 1
                stats['peak_inflight'] = max(stats['peak_inflight'], active)
            phase = 'connect' if writer is None else 'write'
            try:
                async with asyncio.timeout(spec['timeout_seconds']):
                    if writer is None:
                        reader, writer = await asyncio.open_connection('127.0.0.1', spec.get('target_port', 8443 if spec['tls'] else 8080),
                                                                       ssl=context, server_hostname='alpha.test' if context else None,
                                                                       limit=65536)
                    phase = 'write'
                    writer.write(raw)
                    await writer.drain()
                    phase = 'response'
                    closing = await response(reader, expected, spec['gzip'])
                    stats['all_successes'] += 1
                    finished = time.monotonic()
                    if measured:
                        stats['successes'] += 1
                        histogram[min(BINS - 1, math.ceil((finished - started) * 10000))] += 1
                        if finished <= end:
                            stats['completed_in_window'] += 1
                            stats['payload_bytes'] += len(expected)
                    if closing or not spec['persistent']:
                        writer.close()
                        writer = None
            except Exception as error:
                if measured:
                    stats['failures'] += 1
                    stats['timeouts'] += int(isinstance(error, TimeoutError))
                    if isinstance(error, TimeoutError):
                        reason = 'timeout_' + phase
                    elif isinstance(error, ResponseFailure):
                        reason = str(error)
                    elif isinstance(error, (OSError, asyncio.IncompleteReadError)):
                        reason = 'connection_' + phase
                    else:
                        reason = 'protocol'
                    stats['failure_classes'][reason] += 1
                if writer:
                    writer.close()
                writer = reader = None
                await asyncio.sleep(0.001)
            finally:
                if measured:
                    active -= 1
        if writer:
            writer.close()

    await asyncio.gather(lag_monitor(), *(client() for _ in range(clients)))
    stats['cpu_seconds'] = time.process_time() - cpu_start
    stats['elapsed_seconds'] = max(0, time.monotonic() - start_at)
    stats['rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return stats


def worker(spec, clients, start_at, cpu, path, client_binary=None):
    os.sched_setaffinity(0, {cpu})
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, max(soft, 16384)), hard))
    if client_binary is not None:
        raw, expected = request_bytes(spec)
        with os.fdopen(os.memfd_create('toksec-workload'), 'w+b') as inputs:
            inputs.write(f'{len(raw)} {len(expected)}\n'.encode() + raw + expected)
            inputs.seek(0)
            with open(path, 'w') as output:
                os.dup2(inputs.fileno(), 0)
                os.dup2(output.fileno(), 1)
                times = (start_at, spec['warmup_seconds'], spec['seconds'], spec['timeout_seconds'])
                os.execv(client_binary, [str(client_binary), str(clients), str(spec.get('target_port', 8080)),
                                         *[str(round(t * 1_000_000_000)) for t in times]])
    result = asyncio.run(load(spec, clients, start_at))
    with open(path, 'w') as stream:
        json.dump(result, stream)


def proc_sample(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        cpu = (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')
        status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        rss = int(status.get('VmRSS', '0 kB').split()[0])
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
        return cpu, rss, len(children)
    except (OSError, ValueError):
        return 0, 0, 0


def round_run(workload, pid, server_cpu, temporary, upstream_pid=None, upstream_cpu=None, calibration_target=None, client_binary=None):
    from pathlib import Path
    cpus = sorted(os.sched_getaffinity(0) - {server_cpu, upstream_cpu})
    if len(cpus) < 4 or resource.getrlimit(resource.RLIMIT_NOFILE)[1] < 16384:
        raise RuntimeError('benchmark needs four generator CPUs plus one server CPU and descriptor hard limit >=16384')
    spec = asdict(workload)
    if calibration_target == 'origin':
        spec['target_port'] = 8081
        spec['path'] = '/data/' + str(workload.size)
        spec['request_path'] = '/upload' if workload.id.startswith('gateway-16-') else spec['path']
    processes = []
    start = time.monotonic() + 0.5
    cpu_before, peak_rss, child_count = proc_sample(pid)
    upstream_before = proc_sample(upstream_pid)[0] if upstream_pid else 0
    upstream_window = []
    context = multiprocessing.get_context('fork')
    for i in range(4):
        path = Path(temporary) / f'load-{i}.json'
        process = context.Process(target=worker, args=(spec, workload.clients // 4, start, cpus[i], str(path), client_binary))
        process.start()
        processes.append((process, path))
    timeout = start + workload.warmup_seconds + workload.seconds + workload.timeout_seconds + 10
    try:
        while any(p.is_alive() for p, _ in processes):
            cpu_after, rss, children = proc_sample(pid)
            now = time.monotonic()
            if upstream_pid and start + workload.warmup_seconds <= now <= start + workload.warmup_seconds + workload.seconds:
                sample = (now, proc_sample(upstream_pid)[0])
                if not upstream_window:
                    upstream_window.append(sample)
                if len(upstream_window) == 1:
                    upstream_window.append(sample)
                else:
                    upstream_window[1] = sample
            peak_rss = max(peak_rss, rss)
            child_count = max(child_count, children)
            if time.monotonic() > timeout:
                raise TimeoutError('load generators exceeded deadline')
            time.sleep(0.02)
        parts = []
        for process, path in processes:
            process.join()
            if process.exitcode != 0:
                raise RuntimeError('load generator failed')
            parts.append(json.loads(path.read_text()))
    finally:
        for process, _ in processes:
            if process.is_alive():
                process.kill()
            process.join()
    cpu_after, _, _ = proc_sample(pid)
    histogram = [sum(p['histogram'][i] for p in parts) for i in range(BINS)]
    summed = {key: sum(p[key] for p in parts) for key in ('attempts', 'successes', 'all_successes', 'completed_in_window', 'failures', 'timeouts', 'payload_bytes', 'clients_started', 'cpu_seconds', 'rss_kib')}
    overloaded = any(p['cpu_seconds'] / max(0.001, p['elapsed_seconds']) > 0.90 or
                     p['lag_over_20ms'] > max(1, p['lag_samples'] * 0.01) for p in parts)
    failure_classes = Counter()
    for part in parts:
        failure_classes.update(part['failure_classes'])
    upstream_seconds = max(0, proc_sample(upstream_pid)[0] - upstream_before) if upstream_pid else 0
    upstream_utilization = ((upstream_window[-1][1] - upstream_window[0][1]) / max(.001, upstream_window[-1][0] - upstream_window[0][0])) if len(upstream_window) == 2 else 0
    upstream_sample_valid = not upstream_pid or (len(upstream_window) == 2 and upstream_window[-1][0] > upstream_window[0][0])
    upstream_saturated = upstream_utilization > .90
    return {'generator_implementation': 'native_epoll' if client_binary is not None else 'python_asyncio',
            'upstream_cpu': upstream_cpu, 'upstream_cpu_seconds': upstream_seconds,
            'upstream_sample_valid': upstream_sample_valid, 'upstream_utilization': upstream_utilization, 'upstream_saturated': upstream_saturated, **summed, 'valid_rps': summed['completed_in_window'] / workload.seconds,
            'server_cpu': server_cpu, 'generator_cpus': cpus[:4], 'load_average': list(os.getloadavg()),
            'bytes_per_second': summed['payload_bytes'] / workload.seconds,
            'p50_ms': percentile(histogram, 0.50), 'p95_ms': percentile(histogram, 0.95),
            'p99_ms': percentile(histogram, 0.99), 'server_cpu_seconds': max(0, cpu_after - cpu_before),
            'server_peak_rss_kib': peak_rss, 'generator_lag_max_ms': max(p['lag_max_ms'] for p in parts),
            'generator_saturated': overloaded, 'server_child_processes': child_count,
            'generator_utilization_max': max(p['cpu_seconds'] / max(.001, p['elapsed_seconds']) for p in parts),
            'failure_classes': dict(failure_classes),
            'sum_worker_peak_inflight': sum(p['peak_inflight'] for p in parts),
            'eligible': not overloaded and upstream_sample_valid and not upstream_saturated and child_count == 0 and summed['clients_started'] == workload.clients and summed['attempts'] > 0}


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _round_issues(row, workload):
    if not isinstance(row, dict):
        return {'missing_samples'}
    issues = set()
    if row.get('generator_saturated') is True:
        issues.add('generator_saturated')
    if row.get('upstream_saturated') is True:
        issues.add('upstream_saturated')
    if row.get('effects_verified') is False:
        issues.add('effects_unverified')
    if row.get('upstream_sample_valid') is False:
        issues.add('upstream_sample_missing')
    if row.get('server_child_processes', 0):
        issues.add('server_child_processes')
    if row.get('failures') != 0:
        issues.add('request_failures' if row.get('failures') else 'missing_samples')
    if row.get('timeouts', 0):
        issues.add('timeouts')
    if not _positive(row.get('valid_rps')) or not _positive(row.get('p99_ms')):
        issues.add('no_valid_delivery')
    if workload is not None:
        if row.get('clients_started') != workload.clients:
            issues.add('client_count')
        if (type(row.get('generator_saturated')) is not bool or type(row.get('upstream_saturated')) is not bool
                or row.get('upstream_sample_valid') is not True):
            issues.add('missing_samples')
        counts = [row.get(field) for field in ('attempts', 'successes', 'failures', 'timeouts', 'completed_in_window')]
        if any(type(value) is not int or value < 0 for value in counts):
            issues.add('missing_samples')
        else:
            attempts, successes, failures, timeouts, delivered = counts
            if attempts != successes + failures or timeouts > failures or delivered > successes:
                issues.add('invalid_counts')
            if not delivered:
                issues.add('no_valid_delivery')
        if workload.id.startswith('gateway-') and row.get('effects_verified') is not True:
            issues.add('effects_unverified')
    if row.get('eligible') is not True and not issues:
        issues.add('measurement_ineligible')
    return issues


def cell_issues(summary, workload=None):
    """Return independent reasons this measured workload cannot provide a score."""
    if not isinstance(summary, dict) or not summary:
        return ['missing_measurement']
    issues = set()
    if summary.get('calibration_qualified') is False:
        issues.add('calibration_unqualified')
    if summary.get('provisional'):
        issues.add('provisional')
    if summary.get('failures') != 0:
        issues.add('request_failures' if summary.get('failures') else 'missing_samples')
    rows = summary.get('rounds', [])
    if not isinstance(rows, list):
        return sorted(issues | {'incomplete_rounds'})
    if workload is not None and len(rows) != workload.rounds:
        issues.add('incomplete_rounds')
    for row in rows:
        issues.update(_round_issues(row, workload))
    if not _positive(summary.get('median_rps')) or not _positive(summary.get('worst_p99_ms')):
        issues.add('no_valid_delivery')
    if rows and all(isinstance(row, dict) and _positive(row.get('valid_rps')) and _positive(row.get('p99_ms'))
                    for row in rows):
        rates = [row['valid_rps'] for row in rows]
        if (summary.get('median_rps') != statistics.median(rates) or summary.get('min_rps') != min(rates)
                or summary.get('max_rps') != max(rates) or summary.get('worst_p99_ms') != max(row['p99_ms'] for row in rows)):
            issues.add('mismatched_summary')
    if summary.get('eligible') is not True and not issues:
        issues.add('measurement_ineligible')
    return sorted(issues)


def cell_valid(summary, workload=None):
    return not cell_issues(summary, workload)


def matrix_valid(measurements, expected_workloads):
    expected = {w.id: w for w in expected_workloads}
    return (bool(expected) and isinstance(measurements, dict) and set(measurements) == set(expected)
            and all(cell_valid(measurements[name], w) for name, w in expected.items()))


def stage_matrix_valid(measurements, result):
    from toksec.stages import SUPPORTED_STAGES, number
    from toksec.specification import workloads
    if 'stage' not in result and 'level' not in result:
        return False
    stage = number(result)
    return stage != 10 and stage in SUPPORTED_STAGES and matrix_valid(measurements, workloads(stage))


def summarize(rounds, workload=None):
    values = [r['valid_rps'] for r in rounds]
    failures = Counter()
    for row in rounds:
        failures.update(row.get('failure_classes', {}))
    summary = {'rounds': rounds, 'median_rps': statistics.median(values), 'min_rps': min(values), 'max_rps': max(values),
               'worst_p99_ms': max(r['p99_ms'] for r in rounds) if all(r['p99_ms'] is not None for r in rounds) else None,
               'failures': sum(r['failures'] for r in rounds), 'eligible': all(r['eligible'] for r in rounds),
               'timeouts': sum(r.get('timeouts', 0) for r in rounds), 'failure_classes': dict(failures)}
    for source, dest, reduce in (
        ('p95_ms', 'median_p95_ms', statistics.median),
        ('server_cpu_seconds', 'median_cpu_seconds', statistics.median),
        ('server_peak_rss_kib', 'median_rss_kib', statistics.median),
        ('bytes_per_second', 'median_bytes_per_second', statistics.median),
        ('upstream_utilization', 'upstream_utilization_max', max),
        ('generator_lag_max_ms', 'generator_lag_max_ms', max),
        ('generator_utilization_max', 'generator_utilization_max', max),
    ):
        metrics = [r.get(source) for r in rounds]
        summary[dest] = reduce(metrics) if all(v is not None for v in metrics) else None
    summary['validity_reasons'] = cell_issues(summary, workload)
    return summary


def compare(incumbent, challenger, expected_workloads=None):
    if not incumbent or set(incumbent) != set(challenger):
        return {'promote': False, 'reason': 'complete matching workload sets required'}
    expected = ({w.id: w for w in expected_workloads} if expected_workloads is not None
                else dict.fromkeys(incumbent))
    if set(incumbent) != set(expected):
        return {'promote': False, 'reason': 'complete matching workload sets required'}
    if not all(cell_valid(challenger[k], w) for k, w in expected.items()):
        return {'promote': False, 'reason': 'challenger has unqualified measurements'}
    if not all(cell_valid(incumbent[k], w) for k, w in expected.items()):
        return {'promote': True, 'reason': 'first qualified comparison baseline'}
    ratios = []
    for name, old in incumbent.items():
        new = challenger[name]
        if new['worst_p99_ms'] > old['worst_p99_ms'] * 1.05:
            return {'promote': False, 'reason': 'tail-latency regression'}
        if new['min_rps'] <= old['max_rps']:
            return {'promote': False, 'reason': 'throughput ranges overlap or regression'}
        ratios.append(new['median_rps'] / max(old['median_rps'], 1e-9))
    gain = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return {'promote': gain >= 1.05, 'geometric_gain': gain, 'reason': 'paired public workload comparison'}
