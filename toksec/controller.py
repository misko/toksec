import hashlib
import json
import platform
import os
import subprocess
import shutil
import time
import uuid
from pathlib import Path

from controller import atomic_json
from toksec import benchmark, campaign, sandbox
from toksec.specification import ROOT, fingerprint, packet, specification, workloads

PUBLIC_FILES = ('__init__.py', 'specification.py', 'checks.py', 'wire.py', 'fixtures.py', 'benchmark.py', 'sandbox.py', 'driver.py')


def read(run, name='state.json'):
    return json.loads((Path(run) / name).read_text())


def validate(run):
    manifest = read(run, 'manifest.json')
    if manifest['fingerprint'] != fingerprint():
        raise ValueError('framework changed since preparation; prepare a fresh run')
    return manifest


def prepare(directory, level, wall_seconds=1800):
    specification(level)
    if not 120 <= wall_seconds <= 7200:
        raise ValueError('wall_seconds must be between 120 and 7200')
    if not campaign.status(directory)['can_start_model_call']:
        raise ValueError('campaign is unavailable')
    run = Path(directory).resolve() / 'runs' / f'level-{level}-{uuid.uuid4().hex[:12]}'
    (run / 'candidates').mkdir(parents=True)
    (run / 'public-suite' / 'toksec').mkdir(parents=True)
    for name in PUBLIC_FILES:
        shutil.copyfile(ROOT / 'toksec' / name, run / 'public-suite' / 'toksec' / name)
    (run / 'launch-packet.md').write_text(packet(level))
    atomic_json(run / 'specification.json', specification(level))
    atomic_json(run / 'manifest.json', {'level': level, 'campaign': str(Path(directory).resolve()),
                'fingerprint': fingerprint(), 'wall_seconds': wall_seconds, 'started_unix': None,
                'prepared_unix': time.time(), 'platform': platform.platform(),
                'toolchain': str(sandbox.toolchain()),
                'compiler': subprocess.check_output(['rustc', '--version', '--verbose'], text=True),
                'cpu_affinity': sorted(os.sched_getaffinity(0)), 'load_average': list(os.getloadavg())})
    atomic_json(run / 'state.json', {'best': None, 'full_acceptance': False, 'last': None,
                                    'optimization_attempts': 0, 'finished': False})
    return {'run': str(run), 'level': level, 'launch_packet': str(run / 'launch-packet.md')}


def capacity(run):
    manifest = validate(run)
    result = campaign.status(manifest['campaign'])
    started = manifest['started_unix']
    remaining = max(0, manifest['wall_seconds'] - (time.time() - started)) if started else manifest['wall_seconds']
    result.update(seconds_remaining=remaining, best_candidate=read(run)['best'],
                  full_acceptance=read(run)['full_acceptance'], optimization_attempts=read(run)['optimization_attempts'])
    result['can_start_model_call'] &= remaining > 30 and not read(run)['finished']
    return result


def passed(report):
    return {c['id'] for c in report.get('checks', {}).get('cases', []) if c['passed']}


def submit(run, source):
    run = Path(run)
    manifest = validate(run)
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    identity = uuid.uuid4().hex
    artifact = run / 'candidates' / identity
    report = {'id': identity, 'build': sandbox.build(source, artifact, manifest['level']),
              'checks': {'passed': False, 'cases': []}, 'capacity_at_submission': capacity(run)}
    if report['build']['passed']:
        try:
            report['checks'] = sandbox.evaluate(artifact, manifest['level'])
        except (RuntimeError, OSError, ValueError) as error:
            report['checks']['error'] = str(error)[:2000]
    report['source_sha256'] = hashlib.sha256((artifact / 'main.rs').read_bytes()).hexdigest()
    atomic_json(artifact / 'report.json', report)
    old = read(run / 'candidates' / state['best'], 'report.json') if state['best'] else {}
    if not state['full_acceptance'] and 'bootstrap' in passed(report) and passed(report) > passed(old):
        state.update(best=identity, full_acceptance=report['checks']['passed'])
    state['last'] = identity
    atomic_json(run / 'state.json', state)
    export(run)
    return {**report, 'retained': state['best'] == identity, 'best': state['best']}


def measure(run):
    run = Path(run)
    manifest = validate(run)
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    identity = state['last']
    if not identity or not read(run / 'candidates' / identity, 'report.json')['checks']['passed']:
        raise ValueError('last candidate must pass all public checks before benchmarking')
    level = manifest['level']
    selected = workloads(level)
    incumbent = state['best']
    pair = incumbent != identity
    estimated = sum(w.rounds * (w.warmup_seconds + w.seconds + w.timeout_seconds + 1) for w in selected) * (2 if pair else 1) + 30
    if capacity(run)['seconds_remaining'] < estimated:
        raise ValueError(f'need approximately {estimated:.0f}s remaining for the complete benchmark; incumbent retained')
    collected = {key: {w.id: [] for w in selected} for key in {identity, incumbent}}
    for w in selected:
        for round_index in range(w.rounds):
            order = [incumbent, identity] if pair else [identity]
            if round_index % 2:
                order.reverse()
            for candidate in order:
                result = sandbox.invoke_driver(run / 'candidates' / candidate, level, 'benchmark', workload=w.id, rounds=1)
                collected[candidate][w.id].extend(result[w.id]['rounds'])
            atomic_json(run / 'benchmark-progress.json', collected)
    summaries = {key: {name: benchmark.summarize(rounds) for name, rounds in value.items()} for key, value in collected.items()}
    decision = benchmark.compare(summaries[incumbent], summaries[identity]) if pair else {'promote': False, 'reason': 'initial accepted baseline'}
    result = {'candidate': identity, 'incumbent': incumbent, 'summaries': summaries, 'decision': decision}
    atomic_json(run / 'candidates' / identity / 'benchmark.json', result)
    if pair:
        state['optimization_attempts'] += 1
    if decision['promote']:
        state.update(best=identity, full_acceptance=True)
    atomic_json(run / 'state.json', state)
    export(run)
    return result


def test_source(run, source):
    manifest = validate(run)
    if read(run)['finished']:
        raise ValueError('run is finished')
    artifact = Path(run) / 'unit-tests' / uuid.uuid4().hex
    result = sandbox.build(source, artifact, manifest['level'], test=True)
    if result['passed']:
        result['tests'] = sandbox.self_test(artifact)
    return result


def export(run):
    run = Path(run)
    state = read(run)
    best = state['best']
    result = {'best': best, 'full_acceptance': state['full_acceptance'], 'state': state,
              'capacity': capacity(run), 'artifact': None,
              'warning': None if best else 'No working candidate has passed bootstrap. No working product is claimed.'}
    if best:
        result['artifact'] = str(run / 'candidates' / best)
        result['acceptance'] = read(run / 'candidates' / best, 'report.json')
    atomic_json(run / 'result.json', result)
    return result
