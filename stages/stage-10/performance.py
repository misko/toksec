"""Small ordinary-traffic feedback tool, never a complete Stage 10 grade."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import ssl
import subprocess
import time

from toksec.storage import atomic_json
from toksec.sandbox import cgroup as sandbox
from toksec.stages import module as stage_module
evaluate = stage_module(10, 'api')


async def traffic(fixtures, clients, tls):
    context = ssl.create_default_context(cafile=str(Path(fixtures) / 'tls/ca.pem')) if tls else None
    if context: context.set_alpn_protocols(['http/1.1'])
    start = time.monotonic() + 1
    end = start + 3
    latencies, failures, lag = [], [], []

    async def worker():
        reader = writer = None
        try:
            while time.monotonic() < end:
                begun = time.monotonic()
                try:
                    async with asyncio.timeout(2):
                        if writer is None:
                            options = {'ssl': context, 'server_hostname': 'alpha.test'} if tls else {}
                            reader, writer = await asyncio.open_connection('127.0.0.1', 8443 if tls else 8080, **options)
                        writer.write(b'GET /bench4k.dat HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n\r\n')
                        await writer.drain()
                        raw = await reader.readuntil(b'\r\n\r\n')
                        lines = raw.split(b'\r\n')
                        lengths = [line.split(b':', 1)[1].strip() for line in lines if line.lower().startswith(b'content-length:')]
                        if (lines[0].split()[1:2] != [b'200'] or lengths != [b'4096']
                            or any(line.lower().startswith(b'transfer-encoding:') for line in lines)):
                            raise ValueError('status/framing')
                        if await reader.readexactly(4096) != b'x' * 4096:
                            raise ValueError('payload')
                        ended = time.monotonic()
                        if start <= begun < end:
                            latencies.append((ended - begun) * 1000)
                        if any(line.lower() == b'connection: close' for line in lines):
                            writer.close(); writer = None
                except (TimeoutError, OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as error:
                    failures.append({'phase': 'measurement' if begun >= start else 'warmup', 'type': type(error).__name__})
                    if writer: writer.close()
                    writer = None
        finally:
            if writer: writer.close()

    async def monitor():
        for i in range(300):
            deadline = start + i * .01
            await asyncio.sleep(max(0, deadline - time.monotonic()))
            lag.append(max(0, time.monotonic() - deadline) * 1000)

    await asyncio.gather(monitor(), *(worker() for _ in range(clients)))
    latencies.sort()
    def quantile(fraction):
        return latencies[min(len(latencies)-1, int(len(latencies)*fraction))] if latencies else None
    return {'clients': clients, 'tls': tls, 'body_bytes': 4096, 'seconds': 3,
            'completed_started_in_measurement': len(latencies), 'requests_per_second': len(latencies)/3,
            'p50_ms': quantile(.5), 'p95_ms': quantile(.95), 'p99_ms': quantile(.99),
            'failures': len(failures), 'failure_examples': failures[:10],
            'generator_lag_max_ms': max(lag), 'generator_lag_over_20ms': sum(x > 20 for x in lag),
            'eligible': False, 'scope': 'uncalibrated_single_round_development_diagnostic',
            'limitations': ['single load-generator process', 'latency includes connection setup when reconnecting',
                            'no upstream or mixed-load measurement', 'not comparable with canonical v8 benchmark']}


def measure(artifact, output, clients, tls, cpus):
    if clients not in (256, 4096) or type(tls) is not bool:
        raise ValueError('unsupported diagnostic parameters')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    fixtures = evaluate.fixtures(output / 'fixtures')
    (fixtures / 'www/bench4k.dat').write_bytes(b'x' * 4096)
    result_path = output / 'traffic.json'
    with sandbox.running(artifact, fixtures, cpus=cpus, workers=2, timeout=45) as runtime:
        generators = sorted(set(os.sched_getaffinity(0)) - set(cpus))
        if not generators: raise RuntimeError('separate generator CPU required')
        command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials', '--',
                   '/usr/bin/taskset', '-c', str(generators[0]), '/usr/bin/python3', '-m', 'stages.stage-10.performance',
                   '--fixtures', str(fixtures), '--clients', str(clients), '--output', str(result_path)]
        if tls: command.append('--tls')
        before = (runtime['cgroup'] / 'cpu.stat').read_text()
        done = subprocess.run(command, cwd=evaluate.ROOT, capture_output=True, text=True, timeout=30)
        (output / 'driver.log').write_text(done.stdout + done.stderr)
        if done.returncode or not result_path.exists(): raise RuntimeError('diagnostic driver failed')
        result = json.loads(result_path.read_text())
        result['process_tree'] = {'cpu_before': before, 'cpu_after': (runtime['cgroup']/'cpu.stat').read_text(),
                                 'peak_memory_bytes': int((runtime['cgroup']/'memory.peak').read_text()),
                                 'limits': runtime['limits']}
        atomic_json(output / 'result.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--fixtures', required=True); p.add_argument('--clients', type=int, required=True)
    p.add_argument('--tls', action='store_true'); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); atomic_json(a.output, asyncio.run(traffic(a.fixtures, a.clients, a.tls)))
