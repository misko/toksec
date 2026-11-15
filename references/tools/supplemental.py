#!/usr/bin/env python3
"""Host-only native HTTP diagnostic. Official full-suite results remain canonical."""
import argparse
from collections import Counter
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from toksec import sandbox
from toksec.benchmark import BINS, percentile, proc_sample
from toksec.checks import cases_for, configured_cases, EXTERNAL_CASES
from toksec.specification import configuration, fingerprint, workloads
from toksec.wire import request

SCHEMA = 'toksec-supplemental-native-v2'
GUARD_REVISION = 'v2-upstream-liveness-1'
LABEL = 'Supplemental native closed-loop diagnostic; not comparable to canonical asyncio full-suite metrics'
TOOLS = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def accepted(acceptance, source):
    """Reject smoke/subset/stale evidence, including successful-but-incomplete cases."""
    acceptance, source = Path(acceptance).resolve(), Path(source).resolve()
    record = json.loads(acceptance.read_text())
    level, language = record.get('level'), record.get('language')
    if level not in range(1, 6) or language not in ('cpp', 'rust'):
        raise ValueError('acceptance must identify a supported stage and language')
    checks = record.get('checks', {})
    expected = Counter(c.id for c in cases_for(level) + configured_cases(level) + EXTERNAL_CASES)
    actual = Counter(c.get('id') for c in checks.get('cases', []))
    if (not record.get('build', {}).get('passed') or checks.get('passed') is not True
            or checks.get('evaluation_scope') == 'visible_smoke_only'
            or record.get('evaluation_scope') == 'visible_smoke_only'
            or actual != expected or any(c.get('passed') is not True for c in checks.get('cases', []))):
        raise ValueError('successful complete full API acceptance is required')
    if record.get('framework') != fingerprint() or record.get('source_sha256') != digest(source):
        raise ValueError('acceptance does not match current source and framework')
    artifact = acceptance.parent / 'candidate'
    snapshot = artifact / ('main.cpp' if language == 'cpp' else 'main.rs')
    build = json.loads((artifact / 'build.json').read_text())
    binary = artifact / 'server'
    if digest(snapshot) != digest(source) or not build.get('passed') or not binary.is_file() or binary.is_symlink():
        raise ValueError('accepted artifact source/build does not match acceptance')
    return record, artifact


def compile_worker(output):
    command = ['g++', '-std=c++17', '-O3', '-DNDEBUG', '-Wall', '-Wextra', '-Werror',
               str(TOOLS / 'native_load.cpp'), '-o', str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('native diagnostic compile failed: ' + result.stderr[-8000:])
    return {'command': command, 'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
            'source_sha256': digest(TOOLS / 'native_load.cpp'), 'binary_sha256': digest(output)}


def check_cpus(raw, level):
    cpus = [int(cpu) for cpu in raw.split(',')]
    required = 6 if level >= 4 else 5
    if len(cpus) != required or len(set(cpus)) != required or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError(f'exactly {required} distinct available CPUs required (server, four generators, upstream when needed)')
    if cpus[0] != min(cpus):
        raise ValueError('first CPU must be the lowest CPU because sandbox.running pins the server there')
    if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < 16384:
        raise ValueError('descriptor hard limit must be at least 16384')
    return cpus


def aggregate(parts, workload, server, upstream, cpus):
    histogram = [sum(part['histogram'][i] for part in parts) for i in range(BINS)]
    keys = ('attempts', 'successes', 'completed_in_window', 'failures', 'timeouts', 'warmup_failures',
            'payload_bytes', 'clients_started', 'cpu_seconds', 'measurement_cpu_seconds', 'rss_kib')
    summed = {key: sum(part[key] for part in parts) for key in keys}
    accounting = (summed['attempts'] == summed['successes'] + summed['failures']
                  and sum(histogram) == summed['successes']
                  and summed['completed_in_window'] <= summed['successes']
                  and summed['payload_bytes'] == summed['completed_in_window'] * workload['size'])
    saturated = any(part['cpu_seconds'] / max(.001, part['elapsed_seconds']) > .90
                    or part['measurement_cpu_utilization'] > .90
                    or part['expected_lag_samples'] != 300
                    or part['lag_samples'] != part['expected_lag_samples']
                    or not part['lag_coverage_valid']
                    or part['lag_over_20ms'] > max(1, part['lag_samples'] * .01)
                    or part['legacy_lag_samples'] == 0
                    or part['legacy_lag_over_20ms'] > max(1, part['legacy_lag_samples'] * .01)
                    for part in parts)
    upstream_valid = upstream is None or upstream['sample_valid']
    upstream_saturated = upstream is not None and upstream['utilization'] > .90
    reasons = []
    if saturated: reasons.append('generator saturation or excessive event-loop lag')
    if not upstream_valid: reasons.append('missing upstream measurement-window CPU sample')
    if upstream_saturated: reasons.append('upstream utilization above 90%')
    if server['child_processes']: reasons.append('server created child processes')
    if summed['clients_started'] != workload['clients']: reasons.append('not all active clients started')
    if not summed['attempts'] or not summed['completed_in_window']: reasons.append('no measured useful work')
    if not accounting: reasons.append('inconsistent worker accounting')
    if summed['failures']: reasons.append('measured request failures')
    if summed['warmup_failures']: reasons.append('warmup request failures')
    return {**summed, 'histogram': histogram, 'histogram_bin_ms': .1, 'histogram_last_bin_overflow': True,
            'valid_rps': summed['completed_in_window'] / workload['seconds'],
            'bytes_per_second': summed['payload_bytes'] / workload['seconds'],
            'p50_ms': percentile(histogram, .50), 'p95_ms': percentile(histogram, .95),
            'p99_ms': percentile(histogram, .99), 'server': server, 'upstream': upstream,
            'generator_cpus': cpus[1:5], 'server_cpu': cpus[0],
            'upstream_cpu': cpus[5] if len(cpus) == 6 else None,
            'generator_saturated': saturated, 'upstream_saturated': upstream_saturated,
            'generator_lag_max_ms': max(part['lag_max_ms'] for part in parts),
            'sum_worker_peak_inflight': sum(part['peak_inflight'] for part in parts),
            'workers': parts, 'accounting_valid': accounting, 'eligible': not reasons,
            'ineligible_reasons': reasons, 'load_average': list(os.getloadavg())}


def require_upstream_alive(upstream):
    if upstream is not None:
        code = upstream.poll()
        if code is not None:
            raise RuntimeError(f'trusted upstream exited with code {code}; see upstream.stdout.log and upstream.stderr.log')


def run_round(spec, worker, runtime, cpus, directory, upstream):
    require_upstream_alive(upstream)
    upstream_pid = upstream.pid if upstream is not None else None
    raw = directory / 'request.bin'
    raw.write_bytes(request(spec['path'], close=not spec['persistent'], host=spec['host']))
    processes, streams = [], []
    start = time.monotonic_ns() + 1000000000
    measurement_start, end = start / 1e9 + 1, start / 1e9 + 4
    server_pid = runtime['server_pid']
    before = proc_sample(server_pid)
    upstream_before = proc_sample(upstream_pid) if upstream_pid else None
    upstream_rss = upstream_before[1] if upstream_before else 0
    server_window, upstream_window = [], []
    peak_rss, children = before[1:]
    try:
        for index, cpu in enumerate(cpus[1:5]):
            out = (directory / f'worker-{index}.json').open('w')
            err = (directory / f'worker-{index}.stderr').open('w')
            streams.extend((out, err))
            command = [str(worker), '--size', str(spec['size']), '--clients', str(spec['clients'] // 4),
                       '--persistent', str(int(spec['persistent'])), '--cpu', str(cpu), '--port', '8080',
                       '--start-ns', str(start), '--request', str(raw)]
            processes.append(subprocess.Popen(command, stdout=out, stderr=err))
        while any(process.poll() is None for process in processes):
            require_upstream_alive(upstream)
            t = time.monotonic()
            sample = proc_sample(server_pid)
            peak_rss, children = max(peak_rss, sample[1]), max(children, sample[2])
            if measurement_start <= t <= end:
                server_window.append((t, sample[0]))
                if upstream_pid:
                    upstream_sample = proc_sample(upstream_pid)
                    upstream_window.append((t, upstream_sample[0]))
                    upstream_rss = max(upstream_rss, upstream_sample[1])
            if t > end + 5:
                raise TimeoutError('native generators exceeded drain deadline')
            time.sleep(.01)
        require_upstream_alive(upstream)
        for index, process in enumerate(processes):
            if process.returncode:
                raise RuntimeError(f'worker {index} failed: ' + (directory / f'worker-{index}.stderr').read_text()[-2000:])
        for stream in streams: stream.flush()
        parts = [json.loads((directory / f'worker-{index}.json').read_text()) for index in range(4)]
        after = proc_sample(server_pid)
        if not Path(f'/proc/{server_pid}').exists():
            raise RuntimeError('server exited during supplemental measurement')
        def window(samples):
            valid = len(samples) >= 2 and samples[-1][0] - samples[0][0] >= 2.8
            duration = samples[-1][0] - samples[0][0] if len(samples) >= 2 else 0
            used = max(0, samples[-1][1] - samples[0][1]) if len(samples) >= 2 else 0
            return {'sample_valid': valid, 'sample_seconds': duration, 'measurement_cpu_seconds': used,
                    'utilization': used / max(.001, duration)}
        server = {'pid': server_pid, 'cpu_seconds': max(0, after[0] - before[0]), 'peak_rss_kib': peak_rss,
                  'child_processes': children, **window(server_window)}
        require_upstream_alive(upstream)
        upstream_metrics = None if upstream_pid is None else {
            'pid': upstream_pid, 'cpu_seconds': max(0, proc_sample(upstream_pid)[0] - upstream_before[0]),
            'peak_rss_kib': upstream_rss, **window(upstream_window)}
        result = aggregate(parts, spec, server, upstream_metrics, cpus)
        if not server['sample_valid']:
            result['eligible'] = False
            result['ineligible_reasons'].append('missing server measurement-window CPU sample')
        require_upstream_alive(upstream)
        return result
    finally:
        for process in processes:
            if process.poll() is None: process.kill()
            process.wait()
        for stream in streams: stream.close()


def inside(config):
    """Runs in the candidate network/user namespace, retaining host mount/proc view."""
    cpus, runtime = config['cpus'], config['runtime']
    output = Path(config['output'])
    upstream = None
    upstream_streams = []
    try:
        if config['level'] >= 4:
            ready = Path(runtime['fixtures']) / 'supplemental-upstream.ready'
            stdout = (output / 'upstream.stdout.log').open('wb')
            upstream_streams.append(stdout)
            stderr = (output / 'upstream.stderr.log').open('wb')
            upstream_streams.append(stderr)
            upstream = subprocess.Popen(['taskset', '-c', str(cpus[5]), sys.executable, '-m',
                                         'stages.common.smoke.upstream', str(ready)], cwd=ROOT,
                                        stdout=stdout, stderr=stderr)
            deadline = time.monotonic() + 2
            while not ready.exists():
                require_upstream_alive(upstream)
                if time.monotonic() > deadline:
                    raise RuntimeError('trusted benchmark upstream failed to start')
                time.sleep(.01)
            require_upstream_alive(upstream)
        deadline = time.monotonic() + 2
        while True:
            try:
                with socket.create_connection(('127.0.0.1', 8080), .1): break
            except OSError:
                if time.monotonic() > deadline: raise TimeoutError('server did not bind')
                time.sleep(.01)
        if os.sched_getaffinity(runtime['server_pid']) != {cpus[0]}:
            raise RuntimeError('server does not have the declared single CPU affinity')
        if upstream and os.sched_getaffinity(upstream.pid) != {cpus[5]}:
            raise RuntimeError('trusted upstream does not have its dedicated CPU affinity')
        results = {}
        for spec in config['workloads']:
            rounds = []
            for index in range(config['rounds']):
                directory = output / spec['id'] / f'round-{index + 1}'
                directory.mkdir(parents=True)
                rounds.append(run_round(spec, Path(config['worker']), runtime, cpus, directory,
                                        upstream))
                require_upstream_alive(upstream)
                save(output / 'partial.json', results | {spec['id']: {'rounds': rounds, 'incomplete': True}})
            import statistics
            rates = [r['valid_rps'] for r in rounds]
            results[spec['id']] = {'rounds': rounds, 'median_rps': statistics.median(rates),
                                  'min_rps': min(rates), 'max_rps': max(rates),
                                  'worst_p99_ms': max(r['p99_ms'] for r in rounds) if all(r['p99_ms'] is not None for r in rounds) else None,
                                  'failures': sum(r['failures'] for r in rounds),
                                  'eligible': all(r['eligible'] for r in rounds)}
            save(output / 'partial.json', results)
        require_upstream_alive(upstream)
        save(output / 'measurements.json', results)
        require_upstream_alive(upstream)
    finally:
        try:
            if upstream:
                if upstream.poll() is None:
                    upstream.terminate()
                try: upstream.wait(timeout=3)
                except subprocess.TimeoutExpired: upstream.kill(); upstream.wait()
        finally:
            for stream in upstream_streams: stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('measure', 'calibrate', 'internal'))
    parser.add_argument('--acceptance', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--cpus', help='server, four generators, upstream (if stage >=4); scheduling approval is external')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--workload', action='append')
    parser.add_argument('--rounds', type=int, choices=range(1, 6), default=5)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.mode == 'internal':
        inside(json.loads(args.config.read_text()))
        return 0
    if not args.output or not args.cpus: parser.error('--output and --cpus are required')
    record, artifact = (None, None)
    if args.mode == 'measure':
        if not args.acceptance or not args.source: parser.error('measure requires --acceptance and --source')
        record, artifact = accepted(args.acceptance, args.source)
        level = record['level']
    else:
        level = 2
    cpus = check_cpus(args.cpus, level)
    selected = [w for w in workloads(level) if not args.workload or w.id in args.workload]
    if not selected or (args.workload and set(args.workload) != {w.id for w in selected}):
        parser.error('unknown workload selection')
    if any(w.tls or w.gzip or w.clients not in (256, 4096) or w.size not in (4096, 65536)
           or (w.warmup_seconds, w.seconds, w.timeout_seconds) != (1, 3, 2) for w in selected):
        parser.error('native diagnostic supports only the declared plaintext 1+3+2 second workloads')
    output = args.output.resolve()
    # Same lock as the serial official reference launcher: no competing campaigns.
    lockpath = ROOT / '.runs/references/validation.lock'
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    with lockpath.open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: parser.error('another reference evaluation owns the campaign lock')
        os.sched_setaffinity(0, set(cpus))
        output.mkdir(parents=True, exist_ok=False)
        worker = output / 'native_load'
        build = compile_worker(worker)
        if args.mode == 'calibrate':
            artifact = output / 'probe'
            calibration_source = ROOT / 'stages/common/grading/probes/load_reference.cpp'
            calibration_build = sandbox.build(calibration_source.read_text(), artifact, 2, language='cpp')
            if not calibration_build['passed']: raise RuntimeError(calibration_build['diagnostics'])
        binary_hash = digest(artifact / 'server')
        result = {'schema': SCHEMA, 'guard_revision': GUARD_REVISION,
                  'label': LABEL, 'canonical': False, 'comparable_to_official': False,
                  'purpose': 'static generator calibration only; no API or proxy claim' if args.mode == 'calibrate' else 'accepted candidate supplemental diagnostic',
                  'mode': args.mode, 'framework': fingerprint(), 'level': level,
                  'source_sha256': record['source_sha256'] if record else digest(calibration_source),
                  'server_binary_sha256': binary_hash, 'worker_build': build,
                  'orchestrator_sha256': digest(__file__), 'cpus': cpus,
                  'acceptance': str(args.acceptance.resolve()) if record else None,
                  'api_gate_passed': record is not None, 'selected_workloads': [w.id for w in selected],
                  'full_matrix': len(selected) == len(workloads(level)), 'rounds': args.rounds,
                  'timing': {'warmup_seconds': 1, 'measurement_seconds': 3, 'request_timeout_seconds': 2},
                  'one_outstanding_request_per_client': True, 'benchmarks': {}}
        save(output / 'result.json', result)
        values = configuration(level)
        if level == 5: values['cache_ttl_ms'] = '60000'
        override = ''.join(f'{k}={v}\n' for k, v in values.items())
        with sandbox.running(artifact, level, override, smoke=True) as runtime:
            server = sandbox.server_pid(runtime['pid'], artifact)
            config = {'cpus': cpus, 'level': level, 'output': str(output), 'worker': str(worker), 'rounds': args.rounds,
                      'workloads': [asdict(w) for w in selected],
                      'runtime': {'fixtures': str(runtime['fixtures']), 'server_pid': server}}
            config_path = output / 'namespace.json'
            save(config_path, config)
            command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials',
                       '--', sys.executable, '-I', '-B', str(Path(__file__).resolve()), 'internal', '--config', str(config_path)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       start_new_session=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            try:
                stdout, stderr = process.communicate(timeout=len(selected) * args.rounds * 10 + 30)
                (output / 'driver.stdout').write_text(stdout)
                (output / 'driver.stderr').write_text(stderr)
                if process.returncode: raise RuntimeError('supplemental namespace driver failed: ' + stderr[-4000:])
                result['benchmarks'] = json.loads((output / 'measurements.json').read_text())
                result['server_exit_code'] = runtime['process'].poll()
            finally:
                sandbox.kill(process)
                (output / 'server.log').write_bytes((runtime['fixtures'] / 'server.log').read_bytes())
        if digest(artifact / 'server') != binary_hash or (record and accepted(args.acceptance, args.source)[0]['source_sha256'] != record['source_sha256']):
            raise RuntimeError('candidate identity changed during measurement')
        if digest(worker) != build['binary_sha256'] or digest(TOOLS / 'native_load.cpp') != build['source_sha256'] or digest(__file__) != result['orchestrator_sha256']:
            raise RuntimeError('supplemental tool identity changed during measurement')
        result['eligible'] = result['server_exit_code'] is None and all(value['eligible'] for value in result['benchmarks'].values())
        result['proxy_calibration_ready'] = False if args.mode == 'calibrate' else None
        save(output / 'result.json', result)
        print(json.dumps({key: value for key, value in result.items() if key != 'benchmarks'}, indent=2))
        return 0 if result['eligible'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
