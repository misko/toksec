import asyncio
import json
import math
import multiprocessing
import os
import resource
import ssl
import time
import zlib
from pathlib import Path
from dataclasses import asdict

from toksec.wire import payload, request


BINS = 20002


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
    if status != 200 or body != expected:
        raise ValueError('incorrect response')
    return headers.get(b'connection') == b'close'


async def load(spec, clients, start_at):
    histogram = [0] * BINS
    stats = {'attempts': 0, 'successes': 0, 'completed_in_window': 0, 'failures': 0, 'timeouts': 0,
             'payload_bytes': 0, 'peak_inflight': 0, 'clients_started': 0, 'lag_max_ms': 0,
             'lag_samples': 0, 'lag_over_20ms': 0, 'histogram': histogram}
    active = 0
    expected = payload(spec['size'], spec['gzip'])
    raw = request(spec['path'], close=not spec['persistent'], headers={'Accept-Encoding': 'gzip'} if spec['gzip'] else {})
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
            try:
                async with asyncio.timeout(spec['timeout_seconds']):
                    if writer is None:
                        reader, writer = await asyncio.open_connection('127.0.0.1', 8443 if spec['tls'] else 8080,
                                                                       ssl=context, server_hostname='alpha.test' if context else None,
                                                                       limit=65536)
                    writer.write(raw)
                    await writer.drain()
                    closing = await response(reader, expected, spec['gzip'])
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


def worker(spec, clients, start_at, cpu, path):
    os.sched_setaffinity(0, {cpu})
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, max(soft, 16384)), hard))
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


def round_run(workload, pid, server_cpu, temporary):
    from pathlib import Path
    cpus = sorted(os.sched_getaffinity(0) - {server_cpu})
    if len(cpus) < 4 or resource.getrlimit(resource.RLIMIT_NOFILE)[1] < 16384:
        raise RuntimeError('benchmark needs four generator CPUs plus one server CPU and descriptor hard limit >=16384')
    spec = asdict(workload)
    processes = []
    start = time.monotonic() + 0.5
    cpu_before, peak_rss, child_count = proc_sample(pid)
    context = multiprocessing.get_context('fork')
    for i in range(4):
        path = Path(temporary) / f'load-{i}.json'
        process = context.Process(target=worker, args=(spec, workload.clients // 4, start, cpus[i], str(path)))
        process.start()
        processes.append((process, path))
    timeout = start + workload.warmup_seconds + workload.seconds + workload.timeout_seconds + 10
    try:
        while any(p.is_alive() for p, _ in processes):
            cpu_after, rss, children = proc_sample(pid)
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
    summed = {key: sum(p[key] for p in parts) for key in ('attempts', 'successes', 'completed_in_window', 'failures', 'timeouts', 'payload_bytes', 'clients_started', 'cpu_seconds', 'rss_kib')}
    overloaded = any(p['cpu_seconds'] / max(0.001, p['elapsed_seconds']) > 0.90 or
                     p['lag_over_20ms'] > max(1, p['lag_samples'] * 0.01) for p in parts)
    return {**summed, 'valid_rps': summed['completed_in_window'] / workload.seconds,
            'server_cpu': server_cpu, 'generator_cpus': cpus[:4], 'load_average': list(os.getloadavg()),
            'bytes_per_second': summed['payload_bytes'] / workload.seconds,
            'p50_ms': percentile(histogram, 0.50), 'p95_ms': percentile(histogram, 0.95),
            'p99_ms': percentile(histogram, 0.99), 'server_cpu_seconds': max(0, cpu_after - cpu_before),
            'server_peak_rss_kib': peak_rss, 'generator_lag_max_ms': max(p['lag_max_ms'] for p in parts),
            'generator_saturated': overloaded, 'server_child_processes': child_count,
            'sum_worker_peak_inflight': sum(p['peak_inflight'] for p in parts),
            'eligible': not overloaded and child_count == 0 and summed['clients_started'] == workload.clients and summed['attempts'] > 0}


def summarize(rounds):
    import statistics
    values = [r['valid_rps'] for r in rounds]
    return {'rounds': rounds, 'median_rps': statistics.median(values), 'min_rps': min(values), 'max_rps': max(values),
            'worst_p99_ms': max(r['p99_ms'] for r in rounds) if all(r['p99_ms'] is not None for r in rounds) else None,
            'failures': sum(r['failures'] for r in rounds), 'eligible': all(r['eligible'] for r in rounds)}


def compare(incumbent, challenger):
    if not incumbent or set(incumbent) != set(challenger):
        return {'promote': False, 'reason': 'complete matching workload sets required'}
    ratios = []
    for name, old in incumbent.items():
        new = challenger[name]
        if not old['eligible'] or not new['eligible']:
            return {'promote': False, 'reason': 'generator or environment inconclusive'}
        if (new['failures'] or old['failures'] or new['worst_p99_ms'] is None or old['worst_p99_ms'] is None
                or new['worst_p99_ms'] > old['worst_p99_ms'] * 1.05):
            return {'promote': False, 'reason': 'failures or tail-latency regression'}
        if new['min_rps'] <= old['max_rps']:
            return {'promote': False, 'reason': 'throughput ranges overlap or regression'}
        ratios.append(new['median_rps'] / max(old['median_rps'], 1e-9))
    gain = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return {'promote': gain >= 1.05, 'geometric_gain': gain, 'reason': 'paired public workload comparison'}
