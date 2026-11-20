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
from toksec.api import ProviderHTTPError, Responses
from toksec import gateway_turn
from toksec import campaign, controller, context, releases
from toksec.stage_dispatch import stage_of


def tool(name, description, properties=None):
    properties = properties or {}
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}


TOOLS = [tool('init_repository', 'Create a new Git repository inside the sandbox and tag the first working snapshot.'),
         tool('release_candidate', 'Commit and tag the latest validated candidate. You are graded on the latest completed tag if stopped.', {'note': {'type': 'string'}}),
         tool('budget_status', 'Read remaining shared campaign dollars, tokens, wall time and retained candidate.'),
         tool('submit_candidate', 'Compile complete source and run visible smoke checks. A release_note explicitly requests a Git tag on validation; null keeps this submission untagged.', {'source': {'type': 'string'}, 'release_note': {'type': ['string', 'null']}}),
         tool('run_tests', 'Compile and run a standalone unit test in its own sandbox. You supply all code under test. Use run_candidate_test for requests to a submitted server.', {'source': {'type': 'string'}}),
         tool('run_candidate_test', 'Compile your client test, start the submitted server by source hash, then run the client in a separate sandbox against 127.0.0.1:8080. Your client can provide upstream listeners.', {'source_sha256': {'type': 'string'}, 'source': {'type': 'string'}}),
         tool('read_source', 'Read your submitted source by hash. Lines and columns start at 1. Request at most 300 lines and receive at most 24000 characters. To continue a long line, advance start_column.', {'source_sha256': {'type': 'string'}, 'start_line': {'type': 'integer'}, 'start_column': {'type': 'integer'}, 'line_count': {'type': 'integer'}}),
         tool('edit_candidate', 'Replace one exact occurrence of old in the latest source identified by source_sha256. old and new are each limited to 24000 characters. Compile and check the result. Supply release_note to tag on validation, or null.', {'source_sha256': {'type': 'string'}, 'old': {'type': 'string'}, 'new': {'type': 'string'}, 'release_note': {'type': ['string', 'null']}}),
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


def preflight(run, *, resumed=False):
    if stage_of(run) == 10:
        from toksec.accounting import run_allocations
        return run_allocations.preflight(run)
    manifest = controller.validate(run)
    reasons = []
    try:
        controller.read_launch_packet(run, manifest)
    except (OSError, ValueError) as error:
        reasons.append(str(error))
    hint = manifest.get('development_calibration')
    if hint is not None:
        from toksec.calibrations import environment_digest
        from toksec.gateway_calibration import environment, measurement_fingerprint
        if (hint.get('environment_sha256') != environment_digest(environment())
                or hint.get('measurement_fingerprint') != measurement_fingerprint(stage_number(manifest))):
            reasons.append('Development calibration environment or measurement code changed since preparation.')
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
    if manifest['started_unix'] is not None and not resumed:
        reasons.append('Run already started; automatic resumption is disabled.')
    if not resumed and not controller.capacity(run)['can_start_model_call']:
        reasons.append('Campaign budget or state prevents admission.')
    return {'launch_allowed': not reasons, 'reasons': reasons, 'service_tier': 'default',
            'credentials_checked': False, 'model_access_verified': False, 'capacity': controller.capacity(run)}


def dispatch(run, name, args):
    if not isinstance(args, dict):
        raise ValueError('tool arguments must be an object')
    # Accept the source-only call used by earlier clients of submit_candidate.
    if name == 'submit_candidate' and set(args) == {'source'}:
        args = {**args, 'release_note': None}
    expected = {entry['name']: set(entry['parameters']['properties']) for entry in TOOLS}
    if name not in expected or set(args) != expected[name]:
        raise ValueError('unknown tool or arguments')
    if name == 'init_repository':
        return releases.initialize(run)
    if name == 'release_candidate':
        return releases.publish(run, args['note'])
    if name == 'budget_status':
        return controller.capacity(run)
    if name == 'submit_candidate':
        return controller.submit(run, args['source'], args['release_note'])
    if name == 'edit_candidate':
        return controller.edit_candidate(run, args['source_sha256'], args['old'], args['new'], args['release_note'])
    if name == 'read_source':
        return controller.read_candidate_source(run, args['source_sha256'], args['start_line'], args['line_count'], args['start_column'])
    if name == 'run_candidate_test':
        if not isinstance(args['source_sha256'], str):
            raise ValueError('run_candidate_test requires the submitted source_sha256')
        return controller.test_source(run, args['source'], args['source_sha256'])
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


GENERATION_TIMEOUT = 300
FINALIZATION_SECONDS = 30


def _count(client, body, deadline_unix):
    # Both attempts are counts. A generation is sent exactly once.
    for attempt in range(2):
        remaining = deadline_unix - time.time() - FINALIZATION_SECONDS
        if remaining <= 0:
            raise CampaignDeadline('finalization reserve reached')
        try:
            return client.post('responses/input_tokens', body, min(60, remaining))['input_tokens']
        except (TimeoutError, ConnectionError):
            if attempt:
                raise
            time.sleep(min(1, remaining))


def _prepare_turn(run, manifest, directory, client, history, launch_text, bounded, deadline_unix):
    capacity = controller.capacity(run)
    history.append({'role': 'user', 'content': 'Controller capacity ' + json.dumps(context.builder_capacity(capacity))})
    model = manifest.get('model', metering.MODEL)
    request = {'model': model, 'input': history, 'tools': TOOLS}
    options = campaign.profile(model)['prompt_cache_options']
    if bounded:
        from toksec.accounting.counted_requests import validate_request, COUNT_FIELDS
        request.update(reasoning={'effort': 'medium'}, parallel_tool_calls=False,
                       tool_choice='required', truncation='disabled', max_output_tokens=metering.MAX_OUTPUT,
                       service_tier='default', store=False, prompt_cache_options=options)
        validate_request(request)

    count_body = {k: v for k, v in request.items() if k in COUNT_FIELDS} if bounded else request
    count = _count(client, count_body, deadline_unix)
    if count >= (24000 if bounded else context.ROLLOVER_INPUT):
        request['input'] = context.checkpoint(run, launch_text)
        count_body = {k: v for k, v in request.items() if k in COUNT_FIELDS} if bounded else request
        count = _count(client, count_body, deadline_unix)
    if not bounded:
        request = dict(request, reasoning={'effort': 'medium'}, include=['reasoning.encrypted_content'],
                       max_output_tokens=metering.MAX_OUTPUT, service_tier='default', store=False,
                       parallel_tool_calls=False)
        if options is not None:
            request['prompt_cache_options'] = options
    return gateway_turn.prepare(run, directory, request, count, deadline_unix)


def _consume(run, turn, response, bounded):
    history = list(turn['request']['input'])
    output = response['output']
    if bounded:
        visible = [item for item in output if item['type'] in ('message', 'function_call')]
        history.append({'role': 'assistant', 'content': json.dumps(visible)})
    else:
        history.extend(output)
    calls = [item for item in output if item['type'] == 'function_call']
    if not calls:
        if controller.capacity(run)['can_finish']:
            final_text = '\n'.join(part.get('text', '') for item in output for part in item.get('content', [])
                                   if part.get('type') == 'output_text')
            (run / 'model-report.md').write_text(final_text)
            return history, True
        history.append({'role': 'user', 'content': 'Capacity remains. A final message does not end this run. Continue improving the implementation using a tool.'})
        return history, False
    if len(calls) != 1:
        raise ValueError('backend violated sequential tool-call requirement')
    call = calls[0]
    result = gateway_turn.apply_tool(run, turn, response, call, dispatch)
    if bounded:
        history.append({'role': 'user', 'content': json.dumps({'tool': call['name'], 'result': result})})
    else:
        history.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': json.dumps(result)})
    return history, bool(result.get('finished'))


def _deadline_unix(manifest):
    return manifest['started_unix'] + manifest['wall_seconds']


def recovery_status(run, *, settle=False):
    """Inspect the stopped worker. Optionally reconcile a saved receipt without a network call."""
    run = Path(run).resolve()
    if stage_of(run) == 10:
        raise ValueError('gateway recovery is available only for the ordinary runner')
    manifest = controller.validate(run)
    directory = Path(manifest['campaign'])
    with campaign.locked(directory, owner=True):
        if manifest.get('gateway_journal') != 1 or manifest['started_unix'] is None:
            raise ValueError('no resumable gateway run journal')
        deadline_unix = _deadline_unix(manifest)
        recovery = gateway_turn.status(run, directory, deadline_unix)
        turn, entry = gateway_turn.load(run, directory, deadline_unix)
        if settle and entry and entry['state'] == 'reserved':
            if recovery['phase'] == 'reserved_before_dispatch' and time.time() >= deadline_unix - FINALIZATION_SECONDS:
                campaign.begin_send(directory, entry['id'], cancel=True)
                recovery = gateway_turn.status(run, directory, deadline_unix)
            elif (run / f"response-{entry['id']}.json").exists():
                gateway_turn.settle_saved(run, directory, turn)
        state = controller.read(run)
        capacity = controller.capacity(run)
        recovery.update(run_id=run.name, deadline_unix=deadline_unix,
                        seconds_remaining=capacity['seconds_remaining'], stop_kind=state.get('stop_kind'),
                        cpu_affinity=manifest['cpu_affinity'],
                        latest_release=(releases.list_releases(run) or [None])[-1],
                        settled_usd=capacity['spent_usd_upper_bound'], held_usd=capacity['reserved_usd'],
                        available_usd=capacity['remaining_usd'])
        recovery['continuation_possible'] = (
            (not state['finished'] or state.get('interrupted', False))
            and campaign.read(directory)['state'] == 'active'
            and recovery['phase'] not in ('generation_outcome_unknown', 'tool_outcome_unknown', 'cancelled_before_send')
            and not (run / 'gateway-closed.json').exists() and not any(run.glob('evaluation/*/evaluation.json'))
            and capacity['seconds_remaining'] > FINALIZATION_SECONDS
            and (recovery['phase'] not in ('before_first_request', 'counted_before_reservation')
                 or campaign.status(directory, manifest.get('model'))['can_start_model_call']))
        return recovery


def run_loop(run, client, *, resume=False):
    if stage_of(run) == 10:
        if resume:
            raise ValueError('gateway continuation is unavailable for Stage 10')
        from toksec.execution.counted import run_loop as selected
        return selected(run, client)
    run = Path(run).resolve()
    manifest = controller.validate(run)
    directory = Path(manifest['campaign'])
    bounded = campaign.read(directory).get('request_profile') == 'bounded-32k'
    with campaign.locked(directory, owner=True):
        # Re-read under the owner lock. Another process may have finished between validation and lock acquisition.
        manifest = controller.validate(run)
        check = preflight(run, resumed=True) if resume else preflight(run)
        if not check['launch_allowed']:
            raise ValueError('; '.join(check['reasons']))
        text = controller.read_launch_packet(run, manifest)
        pending = None
        entry = None
        if resume:
            state = controller.read(run)
            if (manifest.get('gateway_journal') != 1 or manifest['started_unix'] is None
                    or (state['finished'] and not state.get('interrupted'))
                    or (run / 'gateway-closed.json').exists() or any(run.glob('evaluation/*/evaluation.json'))):
                raise ValueError('run is not open for gateway continuation')
            if (controller.checkout(require_clean=True)['toksec_commit'] != manifest['toksec_commit']
                    or sorted(os.sched_getaffinity(0)) != manifest['cpu_affinity']):
                raise ValueError('continuation requires the original clean checkout and CPU allocation')
            deadline_unix = _deadline_unix(manifest)
            if time.time() >= deadline_unix - FINALIZATION_SECONDS:
                raise ValueError('original run deadline has reached its finalization window')
            recovery = gateway_turn.status(run, directory, deadline_unix)
            if recovery['phase'] in ('generation_outcome_unknown', 'tool_outcome_unknown', 'cancelled_before_send'):
                raise ValueError(f"unresolved {recovery['phase']}; inspect saved receipts before continuing")
            pending, entry = gateway_turn.load(run, directory, deadline_unix)
            state.update(finished=False, interrupted=False)
            state.pop('ended_unix', None)
            atomic_json(run / 'state.json', state)
        else:
            if any(run.glob('candidates/*')) and not manifest.get('starter_candidate'):
                raise ValueError('Measured runs must start with an empty candidate workspace.')
            manifest.update(started_unix=time.time(), gateway_journal=1)
            atomic_json(run / 'manifest.json', manifest)
            deadline_unix = _deadline_unix(manifest)
        if manifest.get('starter_candidate'):
            source = (run / 'starter.rs').read_text()
            import hashlib
            if hashlib.sha256(source.encode()).hexdigest() != manifest['starter_sha256']:
                raise ValueError('starter changed after preparation')
            text += '\nA deliberately limited working bootstrap is supplied below. Its validated snapshot is retained. Complete the public contract before optimizing. This is a server implementation task.\n```rust\n' + source + '\n```\n'
            text += json.dumps(controller.read(run / 'candidates' / manifest['starter_candidate'], 'report.json'))
        history = [{'role': 'developer', 'content': text}]
        reason = 'finished'
        kind = 'finished'
        phase = 'startup'
        interrupted = False
        exception_metadata = {}
        try:
            with deadline(max(0.001, deadline_unix - time.time())):
                while True:
                    if not pending:
                        capacity = controller.capacity(run)
                        if not capacity['can_start_model_call']:
                            reason = 'capacity exhausted or campaign blocked'
                            kind = 'wall_deadline' if capacity['seconds_remaining'] <= FINALIZATION_SECONDS else 'admission_denied'
                            break
                        phase = 'count'
                        pending = _prepare_turn(run, manifest, directory, client, history, text, bounded, deadline_unix)
                    identity = pending['id']
                    if not entry or entry.get('send_phase') == 'not_sent':
                        generation = pending['request']
                        phase = 'reservation'
                        if not entry:
                            campaign.reserve(directory, run.name, pending['counted_input'], generation['model'], intent=pending)
                        timeout = min(GENERATION_TIMEOUT, deadline_unix - time.time() - FINALIZATION_SECONDS)
                        if timeout <= 0:
                            campaign.begin_send(directory, identity, cancel=True)
                            reason, kind = 'finalization reserve reached', 'wall_deadline'
                            break
                        campaign.begin_send(directory, identity)
                        phase = 'generation'
                        if isinstance(client, Responses):
                            response = client.post('responses', generation, timeout, request_id=identity)
                        else:
                            response = client.post('responses', generation, timeout)
                        atomic_json(run / f'response-{identity}.json', response)
                        if isinstance(client, Responses) and client.last_request_id:
                            atomic_json(run / f'transport-{identity}.json',
                                        {'request_id': identity, 'provider_request_id': client.last_request_id})
                    phase = 'settlement'
                    response = gateway_turn.settle_saved(run, directory, pending)
                    if campaign.read(directory)['state'] != 'active':
                        reason, kind = 'usage or model response stopped the campaign', 'settlement_stopped'
                        break
                    phase = 'tool'
                    history, done = _consume(run, pending, response, bounded)
                    if done:
                        break
                    pending, entry = None, None
        except (Exception, KeyboardInterrupt, CampaignDeadline) as error:
            reason = type(error).__name__ + ': ' + str(error)
            interrupted = True
            kind = phase + '_interrupted'
            if isinstance(error, ProviderHTTPError):
                kind = 'provider_429' if error.status == 429 else 'provider_http_error'
                exception_metadata = {'endpoint': error.endpoint, 'http_status': error.status,
                                      'provider_request_id': error.request_id, 'retry_after': error.retry_after}
            elif isinstance(error, TimeoutError):
                kind = phase + '_timeout'
            elif isinstance(error, CampaignDeadline):
                kind = 'wall_deadline'
                interrupted = False
            if pending:
                exception_metadata['local_request_id'] = pending['id']
            if phase == 'generation' and getattr(client, 'last_request_id', None):
                exception_metadata['provider_request_id'] = client.last_request_id
        else:
            interrupted = False
        state = controller.read(run)
        state.update(finished=True, interrupted=interrupted, stop_reason=reason, stop_kind=kind,
                     stop_phase=phase, stop_metadata=exception_metadata, ended_unix=time.time())
        atomic_json(run / 'state.json', state)
        return controller.export(run)


def credentials(path=None):
    key = os.environ.get('OPENAI_API_KEY')
    if path is not None:
        key = Path(path).expanduser().read_text().strip()
    if not key or not key.startswith('sk-') or any(c.isspace() for c in key):
        raise ValueError('Configure OPENAI_API_KEY or provide a file containing only the API key. Never put the key in a prompt.')
    return key
