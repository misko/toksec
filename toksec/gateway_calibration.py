"""Paired controls for parent-owned gateway measurements. No model transport."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import sys
import tempfile
import statistics
import subprocess
import uuid

from stages.common.grading import gateway_fixture
from toksec import benchmark, sandbox
from toksec.provenance import checkout
from toksec.specification import ROOT, fingerprint, workloads
from toksec.storage import atomic_json


def measurement_fingerprint(stage):
    paths = [ROOT / name for name in (
        'toksec/gateway_calibration.py', 'toksec/benchmark.py', 'toksec/driver.py', 'toksec/fixtures.py',
        'toksec/sandbox/__init__.py', 'toksec/wire.py', 'stages/common/grading/performance.py',
        'stages/common/grading/gateway_load.py', 'stages/common/grading/gateway_fixture.py')]
    paths.extend(sorted((ROOT / 'stages/common/grading/probes').glob('*.cpp')))
    paths.extend(sorted((ROOT / 'toksec').glob('*load*.py')))
    paths.append(ROOT / f'stages/stage-{stage:02d}/grading/performance.py')
    paths.append(ROOT / f'stages/stage-{stage:02d}/profile.json')
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def environment():
    affinity = sorted(os.sched_getaffinity(0))
    cgroup_root = Path('/sys/fs/cgroup')
    group = next((s[3:] for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')), '/')
    leaf = cgroup_root / group.lstrip('/')
    limits = []
    for folder in (leaf, *leaf.parents):
        if not folder.is_relative_to(cgroup_root):
            break
        if (folder / 'cpu.max').is_file():
            limits.append({'group': str(folder.relative_to(cgroup_root)), 'cpu_max': (folder / 'cpu.max').read_text().strip()})
    return {'hostname': platform.node(), 'kernel': platform.release(), 'platform': platform.platform(),
            'cpu_affinity': affinity, 'cpu_limits': limits,
            'physical_cores': {str(c): Path(f'/sys/devices/system/cpu/cpu{c}/topology/core_id').read_text().strip()
                               for c in affinity}, 'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0]}


def control_source(source):
    """Spend 35 microseconds of thread CPU on each send in the slow control."""
    return '''#include <sys/socket.h>
#include <time.h>
static long long toksec_control_cpu_ns() {
    struct timespec value;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value);
    return static_cast<long long>(value.tv_sec) * 1000000000 + value.tv_nsec;
}
static ssize_t toksec_slow_send(int fd, const void *bytes, size_t length, int flags) {
    const auto end = toksec_control_cpu_ns() + 35000;
    while (toksec_control_cpu_ns() < end) {}
    return ::send(fd, bytes, length, flags);
}
#define send toksec_slow_send
''' + source


def assess(workload, raw):
    names = ('reference', 'repeat', 'slow_control')
    summaries = {name: benchmark.summarize(raw[name], workload) for name in names}
    reasons = []
    for name, summary in summaries.items():
        for issue in benchmark.cell_issues(summary, workload):
            reasons.append(f'{name}:{issue}')
    ref, repeat, slow = ([r['valid_rps'] for r in raw[n]] for n in names)
    positive = all(r > 0 for values in (ref, repeat, slow) for r in values)
    noise = statistics.median(abs(a - b) / ((a + b) / 2) for a, b in zip(ref, repeat)) if positive else None
    gain = statistics.median((a + b) / (2 * c) - 1 for a, b, c in zip(ref, repeat, slow)) if positive else None
    if noise is None or noise >= .05:
        reasons.append('reference_repeat_variation')
    if gain is None or gain <= max(.05, noise):
        reasons.append('known_slow_control_indistinguishable')
    # A direct ceiling test can saturate its own traffic generator or the target.
    # Verified completed traffic above the in-path rate is a lower bound on capacity.
    # The ordinary reference and slow-control measurements still require no saturation.
    ceiling_targets = ['generator'] if workload.id.startswith('gateway-14-public-') else ['generator', 'origin']
    baseline = statistics.median(ref + repeat)
    for name in ceiling_targets:
        summary = benchmark.summarize(raw[name], replace(workload, rounds=1))
        summaries[name] = summary
        for issue in summary['validity_reasons']:
            if issue not in ('generator_saturated', 'upstream_saturated'):
                reasons.append(f'{name}:{issue}')
        if summary['median_rps'] <= baseline * 1.05:
            reasons.append(f'{name}:insufficient_headroom')
    return {'qualified': not reasons, 'reasons': reasons, 'aa_noise_fraction': noise, 'control_gain_fraction': gain,
            **summaries}


def calibrate(stage, source, output, selected=None, rounds=5):
    declared = {w.id: w for w in workloads(stage)}
    prefix = 'gateway-14-admitted' if stage == 14 else 'gateway-16'
    diagnostic, confirmatory = (f'{prefix}-4096-{c}' for c in (256, 4096))
    chosen = list(dict.fromkeys(selected or [diagnostic, confirmatory, *declared]))
    if any(name not in declared for name in chosen):
        raise ValueError('unknown workload for gateway stage')
    provenance = checkout()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    identity = f'calibration__stage-{stage:02d}__{stamp}__{provenance["toksec_commit"][:12]}__{uuid.uuid4().hex[:8]}'
    output = Path(output or ROOT / 'calibrations' / identity).resolve()
    output.mkdir(parents=True, exist_ok=False)
    data = Path(source).read_text()
    record = {**provenance, 'calibration_id': identity, 'stage': stage, 'status': 'running',
              'environment': environment(), 'measurement_fingerprint': measurement_fingerprint(stage), 'framework': fingerprint(),
              'workloads': {name: asdict(declared[name]) for name in chosen},
              'reference_source_sha256': hashlib.sha256(data.encode()).hexdigest(),
              'diagnostic_workload': diagnostic, 'confirmatory_workload': confirmatory, 'cells': {},
              'declared_rounds': rounds, 'diagnostic_ready': False, 'confirmation_ready': False,
              'full_matrix_ready': False, 'launch_ready': False, 'build': {}, 'api': {},
              'control_description': 'Slow control spends 35 microseconds thread CPU per send, validated by full stage API.',
              'qualification': 'Complete five-round reference/repeat/slow series with zero errors and valid effects; '
                               'median absolute A/A difference below 5%, paired control gain above 5% and noise; direct '
                               'target(s) sustain over 105% of in-path median goodput with correct deliveries.'}
    def save():
        atomic_json(output / 'calibration.json', record)

    save()
    builds = tempfile.TemporaryDirectory(prefix='builds-', dir=output)
    artifacts = Path(builds.name)
    try:
        for label, text in [('reference', data), ('slow_control', control_source(data)), ('generator', gateway_fixture.SOURCE.read_text())]:
            build = sandbox.build(text, artifacts / label, stage, language='cpp')
            record['build'][label] = {**build, 'source_sha256': hashlib.sha256(text.encode()).hexdigest()}
            save()
            if not build['passed']:
                raise RuntimeError(f'{label} did not compile: {build["diagnostics"][-1000:]}')
            if label != 'generator':
                api = sandbox.evaluate(artifacts / label, stage)
                record['api'][label] = api
                save()
                if not api['passed']:
                    raise RuntimeError(f'{label} failed the independent Stage {stage} API')
        for name in chosen:
            w = declared[name]
            raw = {name: [] for name in ('reference', 'repeat', 'slow_control', 'generator', 'origin')}
            def measure(arm):
                probe = arm in ('generator', 'origin')
                artifact = 'generator' if probe else ('reference' if arm == 'repeat' else arm)
                options = {'calibration_target': arm} if probe else {}
                result = sandbox.invoke_driver(artifacts / artifact, stage, 'benchmark', workload=name, rounds=1, **options)
                raw[arm].append(result[name]['rounds'][0])
                atomic_json(output / ('progress-' + name + '.json'), raw)

            measure('generator')
            if not name.startswith('gateway-14-public-'):
                measure('origin')
            # Rotate all three arms, reversing each subsequent block.
            orders = (('reference', 'repeat', 'slow_control'), ('slow_control', 'repeat', 'reference'),
                      ('repeat', 'slow_control', 'reference'), ('reference', 'slow_control', 'repeat'),
                      ('slow_control', 'reference', 'repeat'))
            for i in range(rounds):
                for arm in orders[i % len(orders)]:
                    measure(arm)
            record['cells'][name] = assess(w, raw)
            record['diagnostic_ready'] = record['cells'].get(diagnostic, {}).get('qualified', False)
            record['confirmation_ready'] = record['cells'].get(confirmatory, {}).get('qualified', False)
            save()
            print(name, 'qualified' if record['cells'][name]['qualified'] else record['cells'][name]['reasons'], flush=True, file=sys.stderr)
        if measurement_fingerprint(stage) != record['measurement_fingerprint']:
            raise RuntimeError('measurement code changed during calibration')
        record['full_matrix_ready'] = set(record['cells']) == set(declared) and all(c['qualified'] for c in record['cells'].values())
        record['launch_ready'] = record['diagnostic_ready'] and record['confirmation_ready']
        record['status'] = 'completed'
    except BaseException as error:
        record.update(status='interrupted', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        builds.cleanup()
        save()
        lines = [f'# Stage {stage} gateway calibration', '', f'Calibration ID `{identity}`', '',
                 '| Workload | Qualified | A/A variation | Control gain | Reasons |', '|---|---|---:|---:|---|']
        def pct(value):
            return 'unavailable' if value is None else f'{value:.1%}'
        for name, row in record['cells'].items():
            lines.append(f"| {name} | {row['qualified']} | {pct(row['aa_noise_fraction'])} | {pct(row['control_gain_fraction'])} | {', '.join(row['reasons'])} |")
        lines.extend(['', f"Status `{record['status']}`. See calibration.json for raw rounds, source identity and host configuration.", ''])
        (output / 'report.md').write_text('\n'.join(lines))
    if output.parent == ROOT / 'calibrations':
        from toksec.calibrations import index
        index(output.parent)
    return record
