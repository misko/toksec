import hashlib
import json
import platform
import os
import subprocess
import shutil
import time
import uuid
from pathlib import Path

from toksec.stages import number as stage_number
from toksec.languages import source_name, profile
from toksec.provenance import checkout, run_name, validate_run_id
from toksec.stage_dispatch import stage_of, stage10_tool
from toksec.artifacts import write_artifact, read_artifact, validate_source
from toksec.storage import atomic_json
from toksec.accounting.counted_requests import BudgetLedger
from toksec.sandbox import cgroup
from toksec.stages import module as stage_module
from toksec.specification import counted_fingerprint
from toksec import benchmark, campaign, sandbox
from toksec.specification import ROOT, fingerprint, packet, specification, workloads, instruction_files


def read(run, name='state.json'):
    return json.loads((Path(run) / name).read_text())


def validate(run):
    manifest = read(run, 'manifest.json')
    if manifest['fingerprint'] != fingerprint():
        raise ValueError('framework changed since preparation; prepare a fresh run')
    read_artifact(run, stage_number(manifest), manifest.get('language', 'rust'), manifest.get('artifact_sha256'))
    return manifest


def prepare(directory, level, wall_seconds=1800, model=None, starter=None, spend_target_usd=None, language='rust'):
    if level == 10:
        if starter is not None: raise ValueError('All stages start without starter code')
        from toksec.accounting import run_allocations
        return run_allocations.prepare(directory, language, wall_seconds, model or campaign.TERRA, spend_target_usd)
    model = model or 'gpt-6-luna'
    specification(level, language)
    if starter is not None:
        raise ValueError("All stages start without starter code")
    if not 120 <= wall_seconds <= 7200:
        raise ValueError('wall_seconds must be between 120 and 7200')
    if not campaign.status(directory, model)['can_start_model_call']:
        raise ValueError('campaign is unavailable')
    provenance = checkout(require_clean=True)
    run = Path(directory).resolve() / 'runs' / run_name(level, language, provenance['toksec_commit'])
    (run / 'candidates').mkdir(parents=True)
    for name in instruction_files(level, language):
        destination = run / 'builder-inputs' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_artifact(run, level, language)
    (run / 'launch-packet.md').write_text(packet(level, language))
    atomic_json(run / 'specification.json', specification(level, language))
    atomic_json(run / 'manifest.json', {**provenance, 'run_id': run.name, 'stage': level, 'language': language, 'model': model, 'reasoning_effort': 'medium', 'builder_evaluation_scope': 'visible_smoke_only', 'billing_profile': campaign.profile(model, campaign.read(directory).get('request_profile', 'legacy')), 'campaign': str(Path(directory).resolve()),
                'spend_target_usd': spend_target_usd, 'fingerprint': fingerprint(), 'wall_seconds': wall_seconds, 'started_unix': None,
                'prepared_unix': time.time(), 'platform': platform.platform(),
                'artifact_sha256': hashlib.sha256((run / 'artifact.json').read_bytes()).hexdigest(),
                'input_sha256': {str(p.relative_to(run / 'builder-inputs')): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (run / 'builder-inputs').rglob('*') if p.is_file()},
                'toolchain': str(sandbox.toolchain()) if language == 'rust' else '/usr/bin/g++',
                'compiler': subprocess.check_output([profile(language, level)['compiler'], '--version'], text=True),
                'cpu_affinity': sorted(os.sched_getaffinity(0)), 'load_average': list(os.getloadavg())})
    atomic_json(run / 'state.json', {'best': None, 'smoke_passed': False, 'last': None,
                                    'optimization_attempts': 0, 'finished': False, 'context_rollovers': 0,
                                    'invalidated': [], 'journal_entries': 0})
    return {'run': str(run), 'stage': level, 'launch_packet': str(run / 'launch-packet.md')}


def capacity(run):
    if stage_of(run) == 10:
        return counted_capacity(run)
    manifest = validate(run)
    result = campaign.status(manifest['campaign'], manifest.get('model', 'gpt-6-luna'))
    started = manifest['started_unix']
    remaining = max(0, manifest['wall_seconds'] - (time.time() - started)) if started else manifest['wall_seconds']
    result.update(evaluation_scope=manifest['builder_evaluation_scope'], seconds_remaining=remaining, best_candidate=read(run)['best'],
                  smoke_passed=read(run)['smoke_passed'], optimization_attempts=read(run)['optimization_attempts'])
    target = manifest.get('spend_target_usd')
    if target is not None:
        from decimal import Decimal
        entries = campaign.read(manifest['campaign'])['requests']
        spent = sum((Decimal(r['usage']['cost_usd_upper_bound']) for r in entries if r.get('run') == Path(run).name and r['state'] == 'settled'), Decimal(0))
        result['run_spent_usd'] = str(spent)
        result['spend_target_usd'] = target
        result['can_start_model_call'] &= spent < Decimal(str(target))
    admitted = result['can_start_model_call']
    result['can_finish'] = remaining <= 120 or not admitted
    result['work_phase'] = ('stabilize' if remaining <= 120 else
                            'improve' if result['smoke_passed'] else 'conformance')
    result['context_rollovers'] = read(run).get('context_rollovers', 0)
    result['can_start_model_call'] &= remaining > 30 and not read(run)['finished']
    return result


def passed(report):
    return {c['id'] for c in report.get('checks', {}).get('cases', []) if c['passed']}


def submit(run, source):
    if stage_of(run) == 10:
        return stage10_tool(run, 'submit_candidate', {'source': source})
    run = Path(run)
    manifest = validate(run)
    validate_source(source, read_artifact(run, stage_number(manifest), manifest.get('language', 'rust'), manifest.get('artifact_sha256')))
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    identity = uuid.uuid4().hex
    artifact = run / 'candidates' / identity
    report = {'id': identity, 'build': sandbox.build(source, artifact, stage_number(manifest), language=manifest.get('language', 'rust')),
              'checks': {'passed': False, 'cases': []}, 'capacity_at_submission': capacity(run), 'evaluation_scope': manifest['builder_evaluation_scope']}
    if report['build']['passed']:
        try:
            report['checks'] = sandbox.evaluate(artifact, stage_number(manifest), smoke=True)
        except (RuntimeError, OSError, ValueError) as error:
            report['checks']['error'] = str(error)[:2000]
    report['source_sha256'] = hashlib.sha256((artifact / source_name(manifest)).read_bytes()).hexdigest()
    atomic_json(artifact / 'report.json', report)
    old = read(run / 'candidates' / state['best'], 'report.json') if state['best'] and state['best'] not in state.get('invalidated', []) else {}
    if not state['smoke_passed'] and 'bootstrap' in passed(report) and passed(report) > passed(old):
        state.update(best=identity, smoke_passed=report['checks']['passed'])
    state['last'] = identity
    atomic_json(run / 'state.json', state)
    export(run)
    return {**report, 'retained': state['best'] == identity, 'best': state['best']}


def measure(run, workload=None):
    if stage_of(run) == 10:
        from toksec.stage_dispatch import stage10_benchmark
        return stage10_benchmark(run, workload)
    run = Path(run)
    manifest = validate(run)
    state = read(run)
    if state['finished']:
        raise ValueError('run is finished')
    identity = state['last']
    if not identity or identity in state.get('invalidated', []) or not read(run / 'candidates' / identity, 'report.json')['checks']['passed']:
        raise ValueError('last candidate must pass all public checks before benchmarking')
    level = stage_number(manifest)
    selected = [w for w in workloads(level) if workload is None or w.id == workload]
    if not selected:
        raise ValueError('unknown workload')
    incumbent = state['best'] or identity
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
    if workload is not None:
        decision = {**decision, 'promote': False, 'reason': 'selected workload diagnostic; full matrix required for baseline promotion'}
    result = {'selected_workloads': [w.id for w in selected], 'complete_matrix': workload is None, 'candidate': identity, 'incumbent': incumbent, 'summaries': summaries, 'decision': decision, 'evaluation_scope': 'development_only_not_final_grade'}
    result['recorded_unix'] = time.time()
    result['capacity'] = capacity(run)
    history = run / 'benchmarks'
    history.mkdir(exist_ok=True)
    atomic_json(history / (uuid.uuid4().hex + '.json'), result)
    atomic_json(run / 'candidates' / identity / 'benchmark.json', result)
    if pair:
        state['optimization_attempts'] += 1
    if decision['promote']:
        state.update(best=identity, smoke_passed=True)
    atomic_json(run / 'state.json', state)
    export(run)
    return result


def test_source(run, source):
    if stage_of(run) == 10:
        return stage10_tool(run, 'run_tests', {'source': source})
    manifest = validate(run)
    if read(run)['finished']:
        raise ValueError('run is finished')
    artifact = Path(run) / 'unit-tests' / uuid.uuid4().hex
    result = sandbox.build(source, artifact, stage_number(manifest), test=True, language=manifest.get('language', 'rust'))
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
    if stage_of(run) == 10:
        from toksec.stage_dispatch import stage10_revalidate
        return stage10_revalidate(run, target)
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
            reports.append(sandbox.evaluate(Path(run) / 'candidates' / identity, stage_number(manifest), smoke=True))
        except (RuntimeError, OSError, ValueError) as error:
            reports.append({'passed': False, 'error': str(error)[:8000]})
        atomic_json(destination, {'candidate': identity, 'passed': False, 'complete': False, 'restarts': reports})
        if not reports[-1]['passed']:
            state['invalidated'] = sorted(set(state.get('invalidated', []) + [identity]))
            if state['best'] == identity:
                state['smoke_passed'] = False
            atomic_json(Path(run) / 'state.json', state)
    result = {'candidate': identity, 'passed': all(r['passed'] for r in reports), 'restarts': reports}
    result['complete'] = True
    atomic_json(destination, result)
    export(run)
    return result


def export(run):
    if stage_of(run) == 10:
        from toksec.releases import counted_final_export as final_export
        return final_export(run)
    run = Path(run)
    state = read(run)
    best = state['best']
    result = {'best': best, 'smoke_passed': state['smoke_passed'], 'state': state,
              'capacity': capacity(run), 'artifact': None,
              'warning': None if best else 'No working candidate has passed bootstrap. No working product is claimed.'}
    if best:
        result['artifact'] = str(run / 'candidates' / best)
        result['acceptance'] = read(run / 'candidates' / best, 'report.json')
        if best in state.get('invalidated', []):
            result['warning'] = 'Retained snapshot failed revalidation. It is not a reliably accepted implementation.'
    from toksec.releases import list_releases
    tagged = list_releases(run)
    result['graded_release'] = tagged[-1] if tagged else None
    result['grading_policy'] = 'Latest completed release tag; untagged candidates are not graded.'
    atomic_json(run / 'result.json', result)
    return result


def counted_prepare(run, language='cpp', wall_seconds=7200, budget='2.00', *, run_id=None):
    input_files = stage_module(10, 'packet').input_files
    packet = stage_module(10, 'packet').packet
    if type(wall_seconds) is not int or not 120 <= wall_seconds <= 7200:
        raise ValueError('wall_seconds must be between 120 and 7200')
    prompt = packet(language, budget)
    provenance = checkout(require_clean=True)
    run_id = run_id or run_name(10, language, provenance['toksec_commit'])
    validate_run_id(run_id, 10, language, provenance['toksec_commit'])
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    (run / 'candidates').mkdir()
    for name, source in input_files(language).items():
        destination = run / 'builder-inputs' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copytree(ROOT / 'stages/stage-10/inputs', run / 'builder-inputs/fixtures')
    write_artifact(run, 10, language)
    (run / 'launch-packet.md').write_text(prompt)
    inventory = {str(p.relative_to(run / 'builder-inputs')): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (run / 'builder-inputs').rglob('*') if p.is_file()}
    atomic_json(run / 'manifest.json', {**provenance, 'run_id': run_id, 'stage': 10, 'model': 'gpt-6.1-terra', 'language': language,
                'reasoning_effort': 'medium', 'service_tier': 'default', 'budget_usd': budget,
                'wall_seconds': wall_seconds, 'created_unix': time.time(), 'started_unix': None,
                'toolchain': subprocess.check_output(['dpkg-query','-W','g++','libssl-dev','libssl3t64'], text=True).strip(),
                'openssl_version': subprocess.check_output(['openssl','version'], text=True).strip(),
                'framework': counted_fingerprint(), 'input_sha256': inventory,
                'artifact_sha256': hashlib.sha256((run / 'artifact.json').read_bytes()).hexdigest(), 'starter': False,
                'scope': 'implementation_experiment_with_partial_independent_validation',
                'api_coverage': 'partial', 'performance_scope': 'provisional',
                'cpus': sorted(os.sched_getaffinity(0))[:1]})
    atomic_json(run / 'state.json', {'latest': None, 'tags': [], 'notes': '', 'last_feedback': {}, 'finished': False})
    BudgetLedger(run / 'budget.sqlite', limit_usd=budget)
    return {'run': str(run), 'prepared': True, 'model_calls': 0}


def counted_capacity(run):
    m, s = read(run, 'manifest.json'), read(run)
    elapsed = time.time() - m['started_unix'] if m['started_unix'] else 0
    budget = BudgetLedger(Path(run) / 'budget.sqlite', limit_usd=m['budget_usd']).report()
    budget.update(remaining_usd=budget['remaining_nanodollars']/1e9, spent_usd_upper_bound=budget['spent_nanodollars']/1e9,
                  held_usd=budget['held_nanodollars']/1e9, request_count=len(budget.pop('requests')))
    return {'budget': budget,
            'seconds_remaining': max(0, m['wall_seconds'] - elapsed), 'latest': s['latest'],
            'last_tag': ({k: s['tags'][-1][k] for k in ('tag','passed_checks')} if s['tags'] else None), 'finished': s['finished'], 'effective_runtime': {'cpu_count': 1, 'memory_mib_aggregate': 512, 'workers': 2, 'tasks_including_supervisor': 4, 'file_descriptors_per_process': 4096, 'scratch_mib': 64}}


def counted_submit(run, source, test=False):
    run = Path(run); m = read(run, 'manifest.json'); state = read(run)
    validate_source(source, read_artifact(run, 10, m['language'], m.get('artifact_sha256')))
    artifact = run / 'candidates' / uuid.uuid4().hex
    result = {'build': cgroup.build(source, artifact, language=m['language'], test=test),
              'id': artifact.name, 'test': test, 'checks': {'passed': False, 'cases': []}}
    if result['build']['passed']:
        if test:
            result['test_result'] = cgroup.self_test(artifact, run / 'builder-inputs/fixtures', language=m['language'])
        else:
            result['checks'] = stage_module(10, 'api').evaluate(artifact, artifact / 'smoke', cpus=m['cpus'])
    atomic_json(artifact / 'report.json', result)
    if not test:
        state['latest'] = artifact.name
        atomic_json(run / 'state.json', state)
    return result


def counted_dispatch(run, name, args):
    from toksec.execution.counted import TOOLS
    from toksec.releases import counted_release
    run = Path(run); m = read(run, 'manifest.json'); state = read(run)
    if state['finished']:
        raise ValueError('run finished')
    allowed = {t['name']: set(t['parameters']['properties']) for t in TOOLS}
    if name not in allowed or not isinstance(args, dict) or set(args) != allowed[name]:
        raise ValueError('unknown tool or arguments')
    if name == 'budget_status': return counted_capacity(run)
    if name == 'submit_candidate': return counted_submit(run, args['source'])
    if name == 'run_tests': return counted_submit(run, args['source'], test=True)
    if name == 'init_repository': return counted_release(run, 'First working release', initialize=True)
    if name == 'release_candidate': return counted_release(run, args['note'])
    source = run / 'candidates' / (state['latest'] or '_missing') / ('main.cpp' if m['language'] == 'cpp' else 'main.rs')
    if name == 'edit_candidate':
        text = source.read_text()
        if not args['old'] or text.count(args['old']) != 1:
            raise ValueError('old must match exactly one nonempty source occurrence')
        return counted_submit(run, text.replace(args['old'], args['new'], 1))
    if name in ('read_source', 'read_input'):
        if name == 'read_input':
            path = args['path']
            if path.startswith('openssl/'):
                source = (Path('/usr/include') / path).resolve()
                if not source.is_relative_to('/usr/include/openssl'):
                    raise ValueError('unapproved header path')
            else:
                if path not in m['input_sha256']:
                    raise ValueError('path is not a supplied input')
                source = run / 'builder-inputs' / path
        start, count = args['start_line'], args['line_count']
        if type(start) is not int or type(count) is not int or start < 1 or not 1 <= count <= 300:
            raise ValueError('line range requires start>=1 and count in 1..300')
        return {'text': '\n'.join(source.read_text().splitlines()[start-1:start-1+count])[:24000]}
    if name == 'record_notes':
        if not isinstance(args['note'], str) or len(args['note']) > 12000:
            raise ValueError('notes must fit 12000 characters')
        state['notes'] = args['note']; atomic_json(run / 'state.json', state)
        return {'saved': True}
    if name == 'benchmark_candidate':
        measure = stage_module(10, 'performance').measure
        if not state['latest']: raise ValueError('no source submitted')
        artifact = source.parent
        if not read(artifact, 'report.json')['checks']['passed']:
            raise ValueError('all visible smoke checks required before diagnostic measurement')
        return measure(artifact, artifact / ('benchmark-' + uuid.uuid4().hex), args['clients'], args['tls'], m['cpus'])
    if name == 'finish':
        cap = counted_capacity(run)
        if cap['seconds_remaining'] > 120 and float(cap['budget'].get('remaining_usd', 0)) >= .08768:
            raise ValueError('capacity remains; continue implementation or validation and retain working tags')
        (run / 'model-report.md').write_text(args['report'][:16000])
        return {'finished': True}
    raise ValueError('unknown tool')
