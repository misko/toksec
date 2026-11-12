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


def prepare(directory, level, wall_seconds=1800, model='gpt-6-luna'):
    specification(level)
    if not 120 <= wall_seconds <= 7200:
        raise ValueError('wall_seconds must be between 120 and 7200')
    if not campaign.status(directory, model)['can_start_model_call']:
        raise ValueError('campaign is unavailable')
    run = Path(directory).resolve() / 'runs' / f'level-{level}-{uuid.uuid4().hex[:12]}'
    (run / 'candidates').mkdir(parents=True)
    (run / 'public-suite' / 'toksec').mkdir(parents=True)
    (run / 'public-suite' / 'prompts').mkdir()
    shutil.copyfile(ROOT / 'prompts/improve.md', run / 'public-suite' / 'prompts/improve.md')
    for name in PUBLIC_FILES:
        shutil.copyfile(ROOT / 'toksec' / name, run / 'public-suite' / 'toksec' / name)
    (run / 'launch-packet.md').write_text(packet(level))
    atomic_json(run / 'specification.json', specification(level))
    atomic_json(run / 'manifest.json', {'level': level, 'model': model, 'reasoning_effort': 'medium', 'billing_profile': campaign.profile(model), 'campaign': str(Path(directory).resolve()),
                'fingerprint': fingerprint(), 'wall_seconds': wall_seconds, 'started_unix': None,
                'prepared_unix': time.time(), 'platform': platform.platform(),
                'toolchain': str(sandbox.toolchain()),
                'compiler': subprocess.check_output(['rustc', '--version', '--verbose'], text=True),
                'cpu_affinity': sorted(os.sched_getaffinity(0)), 'load_average': list(os.getloadavg())})
    atomic_json(run / 'state.json', {'best': None, 'full_acceptance': False, 'last': None,
                                    'optimization_attempts': 0, 'finished': False, 'context_rollovers': 0,
                                    'invalidated': [], 'journal_entries': 0})
    return {'run': str(run), 'level': level, 'launch_packet': str(run / 'launch-packet.md')}


def capacity(run):
    manifest = validate(run)
    result = campaign.status(manifest['campaign'], manifest.get('model', 'gpt-6-luna'))
    started = manifest['started_unix']
    remaining = max(0, manifest['wall_seconds'] - (time.time() - started)) if started else manifest['wall_seconds']
    result.update(seconds_remaining=remaining, best_candidate=read(run)['best'],
                  full_acceptance=read(run)['full_acceptance'], optimization_attempts=read(run)['optimization_attempts'])
    admitted = result['can_start_model_call']
    result['can_finish'] = remaining <= 120 or not admitted
    result['work_phase'] = ('stabilize' if remaining <= 120 else
                            'improve' if result['full_acceptance'] else 'conformance')
    result['context_rollovers'] = read(run).get('context_rollovers', 0)
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
    old = read(run / 'candidates' / state['best'], 'report.json') if state['best'] and state['best'] not in state.get('invalidated', []) else {}
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
    if not identity or identity in state.get('invalidated', []) or not read(run / 'candidates' / identity, 'report.json')['checks']['passed']:
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


def record_iteration(run, entry):
    validate(run)
    fields = {'category', 'hypothesis', 'change', 'evidence', 'verdict', 'next_action'}
    if set(entry) != fields or entry['category'] not in {'correctness', 'performance', 'security', 'stability'}:
        raise ValueError('invalid iteration fields or category')
    if any(not isinstance(v, str) or len(v) > 2000 for v in entry.values()):
        raise ValueError('iteration fields must be text of at most 2000 characters')
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    journal = Path(run) / 'iterations'
    journal.mkdir(exist_ok=True)
    index = state.get('journal_entries', 0) + 1
    atomic_json(journal / f'{index:04d}.json', dict(entry, recorded_unix=time.time(),
                best=state['best'], last=state['last'], evidence_author='model; not independent verification'))
    state['journal_entries'] = index
    atomic_json(Path(run) / 'state.json', state)
    return {'recorded': index, 'capacity': capacity(run)}


def revalidate(run, target):
    manifest = validate(run)
    if target not in {'incumbent', 'latest'}:
        raise ValueError('target must be incumbent or latest')
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    identity = state['best'] if target == 'incumbent' else state['last']
    if not identity or not read(Path(run) / 'candidates' / identity, 'report.json')['build']['passed']:
        raise ValueError('a compiled candidate is required')
    if capacity(run)['seconds_remaining'] < 90:
        raise ValueError('reserve at least 90 seconds for three restart checks')
    reports = []
    folder = Path(run) / 'revalidations'
    folder.mkdir(exist_ok=True)
    destination = folder / (uuid.uuid4().hex + '.json')
    for _ in range(3):
        try:
            reports.append(sandbox.evaluate(Path(run) / 'candidates' / identity, manifest['level']))
        except (RuntimeError, OSError, ValueError) as error:
            reports.append({'passed': False, 'error': str(error)[:8000]})
        atomic_json(destination, {'candidate': identity, 'passed': False, 'complete': False, 'restarts': reports})
        if not reports[-1]['passed']:
            state['invalidated'] = sorted(set(state.get('invalidated', []) + [identity]))
            if state['best'] == identity:
                state['full_acceptance'] = False
            atomic_json(Path(run) / 'state.json', state)
    result = {'candidate': identity, 'passed': all(r['passed'] for r in reports), 'restarts': reports}
    result['complete'] = True
    atomic_json(destination, result)
    export(run)
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
        if best in state.get('invalidated', []):
            result['warning'] = 'Retained snapshot failed revalidation. It is not a reliably accepted implementation.'
    atomic_json(run / 'result.json', result)
    return result
