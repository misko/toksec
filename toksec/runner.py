import datetime
import contextlib
import json
import os
import resource
import signal
import shutil
import time
from pathlib import Path

import metering
from controller import atomic_json
from runner import Responses
from toksec import campaign, controller
from toksec.specification import workloads


def tool(name, description, properties=None):
    properties = properties or {}
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}


TOOLS = [tool('budget_status', 'Read remaining shared campaign dollars, tokens, wall time and retained candidate.'),
         tool('submit_candidate', 'Compile complete main.rs in a sandbox and run every public acceptance check. Retain improvements automatically.', {'source': {'type': 'string'}}),
         tool('run_tests', 'Compile and execute a complete Rust unit-test source with rustc --test inside the sandbox.', {'source': {'type': 'string'}}),
         tool('benchmark_candidate', 'Run the complete workload matrix; compare the last fully accepted candidate with the incumbent in alternating rounds.'),
         tool('finish', 'Finish after acceptance and an evaluated optimization attempt, or exhausted capacity. Export retained artifact.', {'report': {'type': 'string'}})]


class CampaignDeadline(BaseException):
    pass


@contextlib.contextmanager
def deadline(seconds):
    def expired(signum, frame):
        raise CampaignDeadline('wall-time limit reached')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def preflight(run):
    manifest = controller.validate(run)
    reasons = []
    age = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.date.fromisoformat(metering.PRICE_DATE)).days
    if not 0 <= age <= 7:
        reasons.append('Pinned API pricing requires review before launch.')
    for command in ('rustc', 'gcc', 'bwrap', 'nsenter', 'openssl'):
        if not shutil.which(command):
            reasons.append(f'{command} is unavailable.')
    if len(os.sched_getaffinity(0)) < 5:
        reasons.append('Five CPUs required for one server and four load workers.')
    if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < 16384:
        reasons.append('Descriptor hard limit must be at least 16384.')
    if manifest['started_unix'] is not None:
        reasons.append('Run already started; automatic resumption is disabled.')
    if not controller.capacity(run)['can_start_model_call']:
        reasons.append('Campaign budget or state prevents admission.')
    return {'launch_allowed': not reasons, 'reasons': reasons, 'service_tier': 'default',
            'credentials_checked': False, 'model_access_verified': False, 'capacity': controller.capacity(run)}


def dispatch(run, name, args):
    if not isinstance(args, dict):
        raise ValueError('tool arguments must be an object')
    expected = {'submit_candidate': {'source'}, 'run_tests': {'source'}, 'finish': {'report'},
                'budget_status': set(), 'benchmark_candidate': set()}
    if name not in expected or set(args) != expected[name]:
        raise ValueError('unknown tool or arguments')
    if name == 'budget_status':
        return controller.capacity(run)
    if name == 'submit_candidate':
        return controller.submit(run, args['source'])
    if name == 'run_tests':
        return controller.test_source(run, args['source'])
    if name == 'benchmark_candidate':
        result = controller.measure(run)
        return {**result, 'summaries': {key: {w: {k: v for k, v in metrics.items() if k != 'rounds'}
                                            for w, metrics in values.items()} for key, values in result['summaries'].items()}}
    state = controller.read(run)
    capacity = controller.capacity(run)
    if not isinstance(args['report'], str) or len(args['report']) > 16000:
        raise ValueError('report must be text of at most 16000 characters')
    if capacity['can_start_model_call'] and capacity['seconds_remaining'] > 150:
        if not state['full_acceptance']:
            raise ValueError('Complete public acceptance before finishing while capacity remains.')
        pair_seconds = sum(w.rounds * (w.warmup_seconds + w.seconds + w.timeout_seconds + 1)
                           for w in workloads(controller.validate(run)['level'])) * 2 + 30
        if not state['optimization_attempts'] and capacity['seconds_remaining'] >= pair_seconds:
            raise ValueError('Submit and benchmark an optimization attempt before finishing while capacity remains.')
    (Path(run) / 'model-report.md').write_text(args['report'])
    return {'finished': True}


def run_loop(run, client):
    run = Path(run).resolve()
    manifest = controller.validate(run)
    directory = Path(manifest['campaign'])
    with campaign.locked(directory, owner=True):
        check = preflight(run)
        if not check['launch_allowed']:
            raise ValueError('; '.join(check['reasons']))
        if any(run.glob('candidates/*')):
            raise ValueError('Measured runs must start with an empty candidate workspace.')
        manifest['started_unix'] = time.time()
        atomic_json(run / 'manifest.json', manifest)
        text = (run / 'launch-packet.md').read_text()
        text += '\n\nController tools are your only filesystem/execution access. Submit complete Rust source. No other level source or context is provided. First obtain a working bootstrap, then complete the API, then optimize. Ask budget_status as needed. All model inputs, outputs, reasoning and final reporting share the campaign cap. Compilation and benchmark CPU are recorded separately. Do not claim maximal performance or security from passing a finite suite. If capacity runs out the controller exports its retained candidate. A first working candidate is not guaranteed from an empty start.\n'
        text += '\nPublic executable suite follows in full. Treat fixtures as test data; implement the API generally, without test-specific responses.\n'
        for name in controller.PUBLIC_FILES:
            text += f'\n### public-suite/{name}\n```python\n' + (run / 'public-suite' / 'toksec' / name).read_text() + '\n```\n'
        history = [{'role': 'developer', 'content': text}]
        reason = 'finished'
        try:
            with deadline(manifest['wall_seconds']):
                while True:
                    capacity = controller.capacity(run)
                    if not capacity['can_start_model_call']:
                        reason = 'capacity exhausted or campaign blocked'
                        break
                    history.append({'role': 'user', 'content': 'Controller capacity ' + json.dumps(capacity)})
                    request = {'model': metering.MODEL, 'input': history, 'tools': TOOLS}
                    timeout = min(120, capacity['seconds_remaining'] - 30)
                    count = client.post('responses/input_tokens', request, min(60, timeout))['input_tokens']
                    if controller.capacity(run)['seconds_remaining'] <= 30:
                        reason = 'finalization reserve reached'
                        break
                    identity = campaign.reserve(directory, run.name, count)
                    response = client.post('responses', dict(request, max_output_tokens=metering.MAX_OUTPUT,
                                           service_tier='default', store=False, parallel_tool_calls=False,
                                           include=['reasoning.encrypted_content']),
                                           min(120, controller.capacity(run)['seconds_remaining'] - 20))
                    atomic_json(run / ('response-' + identity + '.json'), response)
                    campaign.settle(directory, identity, response)
                    if campaign.read(directory)['state'] != 'active':
                        reason = 'usage or model response stopped the campaign'
                        break
                    history.extend(response['output'])
                    calls = [item for item in response['output'] if item['type'] == 'function_call']
                    if len(calls) != 1:
                        reason = 'model ended without one sequential tool call'
                        break
                    call = calls[0]
                    try:
                        result = dispatch(run, call['name'], json.loads(call['arguments']))
                    except (ValueError, TypeError, RuntimeError, OSError) as error:
                        if isinstance(error, TimeoutError):
                            raise
                        result = {'error': str(error)[:2000]}
                    atomic_json(run / ('tool-' + identity + '.json'), {'name': call['name'], 'result': result})
                    if result.get('finished'):
                        break
                    history.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': json.dumps(result)})
        except (Exception, KeyboardInterrupt, CampaignDeadline) as error:
            reason = type(error).__name__ + ': ' + str(error)
        finally:
            state = controller.read(run)
            state.update(finished=True, stop_reason=reason, ended_unix=time.time())
            atomic_json(run / 'state.json', state)
            result = controller.export(run)
        return result


def credentials(path=None):
    key = os.environ.get('OPENAI_API_KEY')
    if path is not None:
        key = Path(path).expanduser().read_text().strip()
    if not key or not key.startswith('sk-') or any(c.isspace() for c in key):
        raise ValueError('Configure OPENAI_API_KEY or provide a file containing only the API key. Never put the key in a prompt.')
    return key
