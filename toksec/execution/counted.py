"""Count-before-send request execution with durable reservations."""
import fcntl
import json
from pathlib import Path
import subprocess
import time
from toksec.storage import atomic_json
from toksec.artifacts import read_artifact
from toksec.accounting.counted_requests import BudgetLedger, COUNT_FIELDS
from toksec.runner import tool, deadline, CampaignDeadline
from toksec import controller, releases
from toksec.specification import counted_fingerprint

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


def run_loop(run, client):
    if controller.read(run, 'manifest.json').get('campaign'):
        from toksec.accounting.run_allocations import run_loop as selected
        return selected(run, client)
    with (Path(run) / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _locked_run_loop(run, client)


def _locked_run_loop(run, client):
    run = Path(run); m = controller.read(run, 'manifest.json')
    if m['started_unix'] is not None: raise ValueError('automatic resume is disabled')
    if m['framework'] != counted_fingerprint(): raise ValueError('framework changed after preparation')
    read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    prompt = controller.read_launch_packet(run, m)
    ledger = BudgetLedger(run / 'budget.sqlite', limit_usd=m['budget_usd'])
    m['started_unix'] = time.time(); atomic_json(run / 'manifest.json', m)
    stop = 'wall limit'
    try:
        with deadline(m['wall_seconds']):
            return _campaign_loop(run, client, m, ledger, prompt)
    except CampaignDeadline:
        state = controller.read(run); state.update(finished=True, stop_reason='wall-time limit reached', ended_unix=time.time())
        atomic_json(run / 'state.json', state)
        return releases.counted_final_export(run)


def _campaign_loop(run, client, m, ledger, prompt):
    stop = 'wall limit'
    try:
        while controller.counted_capacity(run)['seconds_remaining'] > 30:
            state = controller.read(run)
            remaining = ledger.report()['remaining_nanodollars']
            output_cap = min(20000, (remaining - 32000 * 2500) // 7500)
            if output_cap < 1024:
                stop = 'budget reservation capacity exhausted'; break
            context = {'capacity': controller.counted_capacity(run), 'notes': state['notes'], 'last_feedback': state['last_feedback'], 'retained_reads': state.get('retained_reads', {}), 'recent_actions': state.get('recent_actions', [])}
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
                send=lambda body: client.post('responses', body, min(600, max(1, controller.counted_capacity(run)['seconds_remaining']-10))))
            number = len(list(run.glob('response-*.json'))) + 1
            atomic_json(run / f'response-{number:04d}.json', response)
            calls = [x for x in response.get('output', []) if x.get('type') == 'function_call']
            if len(calls) != 1:
                feedback = {'error': 'Use exactly one controller tool per response. A text-only answer does not submit or publish source.', 'response_status': response.get('status')}
            else:
                call = calls[0]
                try:
                    feedback = {'tool': call['name'], 'result': controller.counted_dispatch(run, call['name'], json.loads(call['arguments']))}
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    feedback = {'tool': call.get('name'), 'error': str(error)[:4000]}
            atomic_json(run / f'tool-{number:04d}.json', feedback)
            state = controller.read(run); state['last_feedback'] = feedback
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
        state = controller.read(run); state.update(finished=True, stop_reason=stop, ended_unix=time.time())
        atomic_json(run / 'state.json', state)
    return releases.counted_final_export(run)

