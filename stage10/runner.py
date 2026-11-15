"""Metered, sandboxed Stage 10 implementation campaign. No reference source input."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from controller import atomic_json
from runner import Responses
from toksec.releases import git
from toksec.artifacts import write_artifact, read_artifact, validate_source
from toksec.runner import credentials, tool, deadline, CampaignDeadline
from stage10 import evaluate, sandbox
from stage10.budget import BudgetLedger, COUNT_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'proposals/stage10'
TOOLS = [
    tool('budget_status', 'Read remaining metered dollars, tokens, wall time and release state.'),
    tool('submit_candidate', 'Compile your complete source in the sandbox and run ordinary visible smoke.', {'source': {'type': 'string'}}),
    tool('edit_candidate', 'Replace one exact occurrence in your latest source, then compile and run smoke.', {'old': {'type': 'string'}, 'new': {'type': 'string'}}),
    tool('run_tests', 'Compile your standalone test program and execute it in the sandbox. Create your own listeners; no server starts automatically.', {'source': {'type': 'string'}}),
    tool('read_source', 'Read a bounded line range of your latest source.', {'start_line': {'type': 'integer'}, 'line_count': {'type': 'integer'}}),
    tool('read_input', 'Read one allowlisted instruction, example fixture or approved TLS header.', {'path': {'type': 'string'}, 'start_line': {'type': 'integer'}, 'line_count': {'type': 'integer'}}),
    tool('init_repository', 'Create a private Git repository and publish your first bootstrap-passing release.'),
    tool('release_candidate', 'Publish a working numbered tag without losing previously passing visible checks.', {'note': {'type': 'string'}}),
    tool('record_notes', 'Retain your concise implementation/testing plan across request context rebuilds.', {'note': {'type': 'string'}}),
    tool('benchmark_candidate', 'Run a provisional persistent HTTP or HTTPS diagnostic, not a final performance grade.',
         {'clients': {'type': 'integer', 'enum': [256, 4096]}, 'tls': {'type': 'boolean'}}),
    tool('finish', 'Finish in the last 120 seconds or when no further request fits. The last completed Git tag is the submission.', {'report': {'type': 'string'}}),
]


def read(run, name='state.json'):
    return json.loads((Path(run) / name).read_text())


def identity():
    paths = sorted((ROOT / 'stage10').glob('*.py')) + sorted((PACKET / 'builder').rglob('*.md'))
    paths += [ROOT / 'toksec/artifacts.py', ROOT / 'toksec/evaluation_artifacts.py', ROOT / 'stages/common/ARTIFACTS.md']
    paths += sorted((ROOT / 'contracts').glob('*.schema.json'))
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in paths)).hexdigest()


def prepare(run, language='cpp', wall_seconds=7200, budget='2.00'):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    (run / 'candidates').mkdir()
    shutil.copytree(PACKET / 'builder', run / 'builder-inputs/builder')
    shutil.copytree(PACKET / 'fixtures', run / 'builder-inputs/fixtures')
    other = 'rust' if language == 'cpp' else 'cpp'
    (run / 'builder-inputs/builder/languages' / (other + '.md')).unlink()
    contract = write_artifact(run, 10, language)
    shared_instructions = ROOT / 'stages/common/ARTIFACTS.md'
    shutil.copyfile(shared_instructions, run / 'builder-inputs/builder/ARTIFACTS.md')
    preview = (PACKET / 'preview' / (language + '-launch-packet.md')).read_text()
    operational = '''
Operational campaign notice, authoritative over draft availability statements:
This is a Stage 10 implementation experiment with sandboxed compilation, test
execution and ordinary smoke feedback. The full Stage 10 API grader and calibrated
performance matrix remain incomplete. No result claims full-stage acceptance.
You must implement the server, HTTP parsing, configuration, workers and TLS
integration yourself. OpenSSL headers/libraries are supplied, not server code.
No prior implementation is supplied. The controller creates your private Git
repository when you call init_repository after passing bootstrap. Publish periodic
working tags; only your last completed tag is graded. Do not wait until all Stage 10
features work to publish your first tag. Keep improving while capacity remains.
You have a strict $2 total model-spend cap, including input, output, reasoning and
final reporting. Standard service tier and medium reasoning are used. Requests
are counted before admission. A response's reasoning plus text shares its output
limit, so prefer small complete improvements and use edit_candidate as useful.
Your full latest source and notes are retained outside the context. read_source
retrieves it if the context omits it. No shell or network tool accesses the host.
run_tests builds a standalone test executable; it starts no candidate automatically.
read_input accepts artifact.json, packet-relative builder/ or fixtures/ paths and approved
OpenSSL headers under openssl/. Certificate private keys are public test fixtures.
Read capacity to learn effective sandbox task/descriptor limits. These conservative
per-process limits enforce the total descriptor bound across the bounded task tree.
'''
    (run / 'launch-packet.md').write_text(preview + '\n' + operational + '\n' + shared_instructions.read_text()
                                          + '\n## Artifact contract\n\n```json\n' + json.dumps(contract, indent=2, sort_keys=True) + '\n```\n')
    inventory = {str(p.relative_to(run / 'builder-inputs')): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (run / 'builder-inputs').rglob('*') if p.is_file()}
    atomic_json(run / 'manifest.json', {'stage': 10, 'model': 'gpt-6.1-terra', 'language': language,
                'reasoning_effort': 'medium', 'service_tier': 'default', 'budget_usd': budget,
                'wall_seconds': wall_seconds, 'created_unix': time.time(), 'started_unix': None,
                'toolchain': subprocess.check_output(['dpkg-query','-W','g++','libssl-dev','libssl3t64'], text=True).strip(),
                'openssl_version': subprocess.check_output(['openssl','version'], text=True).strip(),
                'framework': identity(), 'input_sha256': inventory,
                'artifact_sha256': hashlib.sha256((run / 'artifact.json').read_bytes()).hexdigest(), 'starter': False,
                'scope': 'implementation_experiment_with_partial_independent_validation',
                'cpus': sorted(os.sched_getaffinity(0))[:1]})
    atomic_json(run / 'state.json', {'latest': None, 'tags': [], 'notes': '', 'last_feedback': {}, 'finished': False})
    BudgetLedger(run / 'budget.sqlite', limit_usd=budget)
    return {'run': str(run), 'prepared': True, 'model_calls': 0}


def capacity(run):
    m, s = read(run, 'manifest.json'), read(run)
    elapsed = time.time() - m['started_unix'] if m['started_unix'] else 0
    budget = BudgetLedger(Path(run) / 'budget.sqlite', limit_usd=m['budget_usd']).report()
    budget.update(remaining_usd=budget['remaining_nanodollars']/1e9, spent_usd_upper_bound=budget['spent_nanodollars']/1e9,
                  held_usd=budget['held_nanodollars']/1e9, request_count=len(budget.pop('requests')))
    return {'budget': budget,
            'seconds_remaining': max(0, m['wall_seconds'] - elapsed), 'latest': s['latest'],
            'last_tag': ({k: s['tags'][-1][k] for k in ('tag','passed_checks')} if s['tags'] else None), 'finished': s['finished'], 'effective_runtime': {'cpu_count': 1, 'memory_mib_aggregate': 512, 'workers': 2, 'tasks_including_supervisor': 4, 'file_descriptors_per_process': 4096, 'scratch_mib': 64}}


def passed(checks):
    return {c['id'] for c in checks.get('cases', []) if c['passed']}


def submit(run, source, test=False):
    run = Path(run); m = read(run, 'manifest.json'); state = read(run)
    validate_source(source, read_artifact(run, 10, m['language'], m.get('artifact_sha256')))
    artifact = run / 'candidates' / uuid.uuid4().hex
    result = {'build': sandbox.build(source, artifact, language=m['language'], test=test),
              'id': artifact.name, 'test': test, 'checks': {'passed': False, 'cases': []}}
    if result['build']['passed']:
        if test:
            result['test_result'] = sandbox.self_test(artifact, run / 'builder-inputs/fixtures', language=m['language'])
        else:
            result['checks'] = evaluate.evaluate(artifact, artifact / 'smoke', cpus=m['cpus'])
    atomic_json(artifact / 'report.json', result)
    if not test:
        state['latest'] = artifact.name
        atomic_json(run / 'state.json', state)
    return result


def release(run, note, initialize=False):
    run = Path(run); state = read(run); m = read(run, 'manifest.json')
    if not state['latest']:
        raise ValueError('submit working source before release')
    artifact = run / 'candidates' / state['latest']; report = read(artifact, 'report.json')
    checks = passed(report['checks'])
    if not report['build']['passed'] or 'bootstrap' not in checks:
        raise ValueError('release must compile and pass bootstrap')
    if state['tags'] and not set(state['tags'][-1]['passed_checks']) <= checks:
        raise ValueError('release would lose previously passing visible checks')
    if not (run / 'repository/.git').exists():
        if not initialize:
            raise ValueError('call init_repository first')
        git(run, 'init', '--initial-branch=main')
    contract = read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    source_name = contract['submission']['source_file']
    source = (artifact / source_name).read_bytes(); digest = hashlib.sha256(source).hexdigest()
    validate_source(source.decode('utf-8'), contract)
    if state['tags'] and state['tags'][-1]['source_sha256'] == digest:
        return state['tags'][-1]
    meta = {'tag': f'release/{len(state["tags"])+1:06d}', 'source_sha256': digest,
            'candidate': state['latest'], 'passed_checks': sorted(checks), 'note': note[:2000],
            'recorded_unix': time.time(), 'capacity': capacity(run), 'scope': 'visible_smoke_only',
            'artifact_sha256': m.get('artifact_sha256')}
    (run / 'repository' / source_name).write_bytes(source)
    atomic_json(run / 'repository/release.json', meta)
    git(run, 'add', source_name, 'release.json'); git(run, 'commit', '-m', meta['tag'])
    git(run, 'tag', meta['tag'])
    state['tags'].append(meta); atomic_json(run / 'state.json', state)
    return meta


def dispatch(run, name, args):
    run = Path(run); m = read(run, 'manifest.json'); state = read(run)
    if state['finished']:
        raise ValueError('run finished')
    allowed = {t['name']: set(t['parameters']['properties']) for t in TOOLS}
    if name not in allowed or not isinstance(args, dict) or set(args) != allowed[name]:
        raise ValueError('unknown tool or arguments')
    if name == 'budget_status': return capacity(run)
    if name == 'submit_candidate': return submit(run, args['source'])
    if name == 'run_tests': return submit(run, args['source'], test=True)
    if name == 'init_repository': return release(run, 'First working release', initialize=True)
    if name == 'release_candidate': return release(run, args['note'])
    source = run / 'candidates' / (state['latest'] or '_missing') / ('main.cpp' if m['language'] == 'cpp' else 'main.rs')
    if name == 'edit_candidate':
        text = source.read_text()
        if not args['old'] or text.count(args['old']) != 1:
            raise ValueError('old must match exactly one nonempty source occurrence')
        return submit(run, text.replace(args['old'], args['new'], 1))
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
        from stage10.benchmark import measure
        if not state['latest']: raise ValueError('no source submitted')
        artifact = source.parent
        if not read(artifact, 'report.json')['checks']['passed']:
            raise ValueError('all visible smoke checks required before diagnostic measurement')
        return measure(artifact, artifact / ('benchmark-' + uuid.uuid4().hex), args['clients'], args['tls'], m['cpus'])
    if name == 'finish':
        cap = capacity(run)
        if cap['seconds_remaining'] > 120 and float(cap['budget'].get('remaining_usd', 0)) >= .08768:
            raise ValueError('capacity remains; continue implementation or validation and retain working tags')
        (run / 'model-report.md').write_text(args['report'][:16000])
        return {'finished': True}
    raise ValueError('unknown tool')


def final_export(run):
    run = Path(run); m, state = read(run, 'manifest.json'), read(run)
    result = {'capacity': capacity(run), 'release_count': len(state['tags']), 'final_grade_eligible': False}
    if state['tags']:
        tag = state['tags'][-1]; name = 'main.cpp' if m['language'] == 'cpp' else 'main.rs'
        source = git(run, 'show', tag['tag'] + ':' + name)
        if hashlib.sha256(source.encode()).hexdigest() != tag['source_sha256']:
            raise ValueError('tag source identity mismatch')
        (run / 'final').mkdir(exist_ok=True); (run / 'final' / name).write_text(source)
        result['last_tag'] = tag
        result['source'] = str(run / 'final' / name)
    else:
        result['no_submission'] = 'No completed working release tag'
    atomic_json(run / 'result.json', result)
    return result


def run_loop(run, client):
    with (Path(run) / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _locked_run_loop(run, client)


def _locked_run_loop(run, client):
    run = Path(run); m = read(run, 'manifest.json')
    if m['started_unix'] is not None: raise ValueError('automatic resume is disabled')
    if m['framework'] != identity(): raise ValueError('framework changed after preparation')
    read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    ledger = BudgetLedger(run / 'budget.sqlite', limit_usd=m['budget_usd'])
    m['started_unix'] = time.time(); atomic_json(run / 'manifest.json', m)
    prompt = (run / 'launch-packet.md').read_text(); stop = 'wall limit'
    try:
        with deadline(m['wall_seconds']):
            return _campaign_loop(run, client, m, ledger, prompt)
    except CampaignDeadline:
        state = read(run); state.update(finished=True, stop_reason='wall-time limit reached', ended_unix=time.time())
        atomic_json(run / 'state.json', state)
        return final_export(run)


def _campaign_loop(run, client, m, ledger, prompt):
    stop = 'wall limit'
    try:
        while capacity(run)['seconds_remaining'] > 30:
            state = read(run)
            remaining = ledger.report()['remaining_nanodollars']
            output_cap = min(20000, (remaining - 32000 * 2500) // 7500)
            if output_cap < 1024:
                stop = 'budget reservation capacity exhausted'; break
            context = {'capacity': capacity(run), 'notes': state['notes'], 'last_feedback': state['last_feedback'], 'retained_reads': state.get('retained_reads', {}), 'recent_actions': state.get('recent_actions', [])}
            if state['latest']:
                path = run / 'candidates' / state['latest'] / ('main.cpp' if m['language'] == 'cpp' else 'main.rs')
                context['latest_source'] = path.read_text() if path.stat().st_size <= 32000 else 'Source retained; use read_source for line ranges.'
            request = {'model': 'gpt-6.1-terra', 'input': [{'role': 'developer', 'content': prompt},
                       {'role': 'user', 'content': json.dumps(context) + '\nTake your next implementation/tool step. Publish a working tag early.'}],
                       'tools': TOOLS, 'max_output_tokens': output_cap, 'service_tier': 'default', 'store': False, 'truncation': 'disabled',
                       'parallel_tool_calls': False, 'tool_choice': 'required', 'reasoning': {'effort': 'medium'},
                       'prompt_cache_options': {'mode': 'implicit', 'ttl': '30m'}}
            count_body = {k: v for k, v in request.items() if k in COUNT_FIELDS}
            count = client.post('responses/input_tokens', count_body, 60)
            if count.get('input_tokens', 0) > 32000:
                context.pop('latest_source', None)
                context['last_feedback'] = json.dumps(context['last_feedback'])[:12000]
                context['notes'] = context['notes'][:8000]
                request['input'][1]['content'] = json.dumps(context) + '\nUse exactly one tool. Source retained via read_source.'
                count_body = {k: v for k, v in request.items() if k in COUNT_FIELDS}
                count = client.post('responses/input_tokens', count_body, 60)
            def counted(body):
                if body != count_body: raise ValueError('count payload mismatch')
                return count
            response = ledger.execute(request,
                count_tokens=counted,
                send=lambda body: client.post('responses', body, min(600, max(1, capacity(run)['seconds_remaining']-10))))
            number = len(list(run.glob('response-*.json'))) + 1
            atomic_json(run / f'response-{number:04d}.json', response)
            calls = [x for x in response.get('output', []) if x.get('type') == 'function_call']
            if len(calls) != 1:
                feedback = {'error': 'Use exactly one controller tool per response. A text-only answer does not submit or publish source.', 'response_status': response.get('status')}
            else:
                call = calls[0]
                try:
                    feedback = {'tool': call['name'], 'result': dispatch(run, call['name'], json.loads(call['arguments']))}
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    feedback = {'tool': call.get('name'), 'error': str(error)[:4000]}
            atomic_json(run / f'tool-{number:04d}.json', feedback)
            state = read(run); state['last_feedback'] = feedback
            if len(calls) == 1:
                call = calls[0]
                arguments = json.loads(call['arguments'])
                if call['name'] == 'read_input' and 'result' in feedback:
                    retained = state.setdefault('retained_reads', {})
                    retained[arguments['path']] = feedback['result']
                    while len(json.dumps(retained)) > 24000:
                        del retained[next(iter(retained))]
                history = state.setdefault('recent_actions', [])
                history.append({'tool': call['name'], 'arguments': {k:v for k,v in arguments.items() if k not in ('source','old','new')}, 'error': feedback.get('error')})
                state['recent_actions'] = history[-12:]
            atomic_json(run / 'state.json', state)
            print(json.dumps({'turn': number, 'tool': feedback.get('tool'), 'budget': ledger.report(), 'tags': len(state['tags'])}), flush=True)
            if feedback.get('result', {}).get('finished'):
                stop = 'agent finished'; break
    except CampaignDeadline:
        stop = 'wall-time limit reached'
    except Exception as error:
        stop = type(error).__name__ + ': ' + str(error)
    finally:
        state = read(run); state.update(finished=True, stop_reason=stop, ended_unix=time.time())
        atomic_json(run / 'state.json', state)
    return final_export(run)



def grade(run, output=None):
    from toksec.evaluation_artifacts import write_evaluation
    run = Path(run)
    output = Path(output) if output is not None else run / 'evaluation' / uuid.uuid4().hex
    if output.resolve().is_relative_to((run / 'repository').resolve()):
        raise ValueError('parent evaluation output cannot be inside the implementation repository')
    m, state = read(run, 'manifest.json'), read(run)
    if not state['tags']:
        raise ValueError('no tagged submission')
    tag = state['tags'][-1]
    contract = read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    name = contract['submission']['source_file']
    source = git(run, 'show', tag['tag'] + ':' + name)
    validate_source(source, contract)
    if hashlib.sha256(source.encode()).hexdigest() != tag['source_sha256']:
        raise ValueError('tag digest mismatch')
    release = {'tag': tag['tag'], 'commit': git(run, 'rev-parse', tag['tag'] + '^{commit}').strip(),
               'source_sha256': tag['source_sha256']}
    output.mkdir(parents=True, exist_ok=False)
    candidate = output / 'candidate'
    built = sandbox.build(source, candidate, language=m['language'])
    checks = evaluate.evaluate(candidate, output / 'api-checks', mode='api', cpus=m['cpus']) if built['passed'] else {'passed': False, 'cases': []}
    result = {'build': built, 'checks': checks, 'release': release,
              'source_sha256': tag['source_sha256'], 'framework': identity(), 'final_grade_eligible': False}
    atomic_json(output / 'result.json', result)
    write_evaluation(output, run_id=run.name, release=release,
                     contract_sha256=m.get('artifact_sha256'), evaluator_sha256=identity(),
                     environment={k: m[k] for k in ('toolchain', 'openssl_version', 'cpus') if k in m},
                     coverage='partial', result=result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'run', 'status', 'grade'])
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--language', choices=['cpp', 'rust'], default='cpp')
    p.add_argument('--key-file', type=Path)
    p.add_argument('--output', type=Path, help='New parent-owned evaluation directory for grade')
    p.add_argument('--budget-usd', default='2.00')
    args = p.parse_args()
    if args.command == 'prepare': result = prepare(args.run, args.language, budget=args.budget_usd)
    elif args.command == 'status': result = capacity(args.run)
    elif args.command == 'grade': result = grade(args.run, args.output)
    else: result = run_loop(args.run, Responses(credentials(args.key_file)))
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
