import datetime
import contextlib
import json
import os
import resource
import signal
import shutil
import time
from pathlib import Path

from toksec.stages import number as stage_number
from toksec import metering
from toksec.storage import atomic_json
from toksec.api import Responses
from toksec import campaign, controller, context, releases
from toksec.stage_dispatch import stage_of


def tool(name, description, properties=None):
    properties = properties or {}
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}


TOOLS = [tool('init_repository', 'Create a new Git repository inside the sandbox and tag the first working snapshot.'),
         tool('release_candidate', 'Commit and tag the latest validated candidate. You are graded on the latest completed tag if stopped.', {'note': {'type': 'string'}}),
         tool('budget_status', 'Read remaining shared campaign dollars, tokens, wall time and retained candidate.'),
         tool('submit_candidate', 'Compile the complete source file for the selected language in a sandbox and run the visible smoke checks. Retain improvements automatically.', {'source': {'type': 'string'}}),
         tool('run_tests', 'Compile and execute your complete test source using the selected language test interface inside the sandbox.', {'source': {'type': 'string'}}),
         tool('benchmark_candidate', 'Compare smoke-passing candidates in alternating rounds. Use null for the full matrix or a declared workload ID for a diagnostic subset.', {'workload': {'type': ['string', 'null']}}),
         tool('revalidate_candidate', 'Check a compiled candidate through three fresh sandbox starts and visible smoke suites. A failure invalidates reliability.', {'target': {'type': 'string', 'enum': ['incumbent', 'latest']}}),
         tool('record_iteration', 'Persist concise experiment notes across context rollover. These notes are model claims, not promotion authority.',
              {'category': {'type': 'string', 'enum': ['correctness', 'performance', 'security', 'stability']},
               **{key: {'type': 'string'} for key in ('hypothesis', 'change', 'evidence', 'verdict', 'next_action')}}),
         tool('finish', 'Export and report only when budget_status.can_finish is true. Acceptance alone never ends improvement.', {'report': {'type': 'string'}})]


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
    if stage_of(run) == 10:
        from toksec.accounting import run_allocations
        return run_allocations.preflight(run)
    manifest = controller.validate(run)
    reasons = []
    age = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.date.fromisoformat(metering.PRICE_DATE)).days
    if not 0 <= age <= 7:
        reasons.append('Pinned API pricing requires review before launch.')
    for command in (('g++', 'gcc', 'readelf', 'nm', 'dpkg-query') if manifest.get('language') == 'cpp' else ('rustc', 'gcc', 'readelf', 'nm')) + ('bwrap', 'nsenter'):
        if not shutil.which(command):
            reasons.append(f'{command} is unavailable.')
    needed_cpus = 6 if stage_number(manifest) >= 4 else 5
    if len(os.sched_getaffinity(0)) < needed_cpus:
        reasons.append(f'{needed_cpus} CPUs required for server, load workers and any upstream fixture.')
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
    expected = {'init_repository': set(), 'release_candidate': {'note'}, 'submit_candidate': {'source'}, 'run_tests': {'source'}, 'finish': {'report'},
                'budget_status': set(), 'benchmark_candidate': {'workload'}, 'revalidate_candidate': {'target'},
                'record_iteration': {'category', 'hypothesis', 'change', 'evidence', 'verdict', 'next_action'}}
    if name not in expected or set(args) != expected[name]:
        raise ValueError('unknown tool or arguments')
    if name == 'init_repository':
        return releases.initialize(run)
    if name == 'release_candidate':
        return releases.publish(run, args['note'])
    if name == 'budget_status':
        return controller.capacity(run)
    if name == 'submit_candidate':
        return controller.submit(run, args['source'])
    if name == 'run_tests':
        return controller.test_source(run, args['source'])
    if name == 'record_iteration':
        return controller.record_iteration(run, args)
    if name == 'revalidate_candidate':
        return controller.revalidate(run, args['target'])
    if name == 'benchmark_candidate':
        result = controller.measure(run, args['workload'])
        return {**result, 'summaries': {key: {w: {k: v for k, v in metrics.items() if k != 'rounds'}
                                            for w, metrics in values.items()} for key, values in result['summaries'].items()}}
    capacity = controller.capacity(run)
    if not isinstance(args['report'], str) or len(args['report']) > 16000:
        raise ValueError('report must be text of at most 16000 characters')
    if not capacity['can_finish']:
        raise ValueError('Capacity remains. Continue improving the implementation using your chosen tests or measurements. Finish is allowed only in the final 120 seconds or when model admission capacity is exhausted.')
    (Path(run) / 'model-report.md').write_text(args['report'])
    return {'finished': True}


def run_loop(run, client):
    if stage_of(run) == 10:
        from toksec.execution.counted import run_loop as selected
        return selected(run, client)
    run = Path(run).resolve()
    manifest = controller.validate(run)
    directory = Path(manifest['campaign'])
    bounded = campaign.read(directory).get('request_profile') == 'bounded-32k'
    with campaign.locked(directory, owner=True):
        check = preflight(run)
        if not check['launch_allowed']:
            raise ValueError('; '.join(check['reasons']))
        if any(run.glob('candidates/*')) and not manifest.get('starter_candidate'):
            raise ValueError('Measured runs must start with an empty candidate workspace.')
        manifest['started_unix'] = time.time()
        atomic_json(run / 'manifest.json', manifest)
        text = (run / 'launch-packet.md').read_text()
        if manifest.get('starter_candidate'):
            source = (run / 'starter.rs').read_text()
            import hashlib
            if hashlib.sha256(source.encode()).hexdigest() != manifest['starter_sha256']:
                raise ValueError('starter changed after preparation')
            text += '\nA deliberately limited working bootstrap is supplied below. Its validated snapshot is retained. Complete the public contract before optimizing. This is a server implementation task.\n```rust\n' + source + '\n```\n'
            text += json.dumps(controller.read(run / 'candidates' / manifest['starter_candidate'], 'report.json'))
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
                    model = manifest.get('model', metering.MODEL)
                    request = {'model': model, 'input': history, 'tools': TOOLS}
                    options = campaign.profile(model)['prompt_cache_options']
                    timeout = min(120, capacity['seconds_remaining'] - 30)
                    if bounded:
                        from toksec.accounting.counted_requests import validate_request, COUNT_FIELDS
                        request.update(reasoning={'effort': 'medium'}, parallel_tool_calls=False,
                                       tool_choice='required', truncation='disabled', max_output_tokens=metering.MAX_OUTPUT,
                                       service_tier='default', store=False, prompt_cache_options=options)
                        validate_request(request)
                    count_request = {k: v for k, v in request.items() if k in COUNT_FIELDS} if bounded else request
                    count = client.post('responses/input_tokens', count_request, min(60, timeout))['input_tokens']
                    if count >= (24000 if bounded else context.ROLLOVER_INPUT):
                        history = context.checkpoint(run, text)
                        request['input'] = history
                        count_request = {k: v for k, v in request.items() if k in COUNT_FIELDS} if bounded else request
                        count = client.post('responses/input_tokens', count_request, min(60, timeout))['input_tokens']
                    if controller.capacity(run)['seconds_remaining'] <= 30:
                        reason = 'finalization reserve reached'
                        break
                    identity = campaign.reserve(directory, run.name, count, model)
                    generation = dict(request, reasoning={'effort': 'medium'})
                    if options is not None:
                        generation['prompt_cache_options'] = options
                    if not bounded:
                        generation['include'] = ['reasoning.encrypted_content']
                    response = client.post('responses', dict(generation, max_output_tokens=metering.MAX_OUTPUT,
                                           service_tier='default', store=False, parallel_tool_calls=False,
                                           ),
                                           min(120, controller.capacity(run)['seconds_remaining'] - 20))
                    atomic_json(run / ('response-' + identity + '.json'), response)
                    campaign.settle(directory, identity, response)
                    if campaign.read(directory)['state'] != 'active':
                        reason = 'usage or model response stopped the campaign'
                        break
                    if bounded:
                        visible = [item for item in response['output'] if item['type'] in ('message', 'function_call')]
                        history.append({'role': 'assistant', 'content': json.dumps(visible)})
                    else:
                        history.extend(response['output'])
                    calls = [item for item in response['output'] if item['type'] == 'function_call']
                    if not calls:
                        if controller.capacity(run)['can_finish']:
                            final_text = '\n'.join(part.get('text', '') for item in response['output']
                                                   for part in item.get('content', []) if part.get('type') == 'output_text')
                            (run / 'model-report.md').write_text(final_text)
                            break
                        history.append({'role': 'user', 'content': 'Capacity remains. A final message does not end this run. Continue improving the implementation using a tool; inspect budget_status if needed.'})
                        continue
                    if len(calls) != 1:
                        raise ValueError('backend violated sequential tool-call requirement')
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
                    if bounded:
                        history.append({'role': 'user', 'content': json.dumps({'tool': call['name'], 'result': result})})
                    else:
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
