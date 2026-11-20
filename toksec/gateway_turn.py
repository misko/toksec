"""Recover the last gateway turn using the durable reservation and local receipts."""
import hashlib
import json
import uuid

from toksec import campaign
from toksec.storage import atomic_json


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def prepare(run, directory, request, count, deadline):
    entries = [r for r in campaign.read(directory)['requests'] if r.get('run') == run.name]
    turn = {'id': uuid.uuid4().hex, 'run': run.name, 'previous_id': entries[-1]['id'] if entries else None,
            'request_sha256': digest(request), 'request': request, 'counted_input': count,
            'max_output_tokens': request['max_output_tokens'], 'deadline_unix': deadline}
    atomic_json(run / 'gateway-turn.json', turn)
    return turn


def load(run, directory, deadline):
    entries = [r for r in campaign.read(directory)['requests'] if r.get('run') == run.name]
    path = run / 'gateway-turn.json'
    if not path.exists():
        if entries:
            raise ValueError('reserved request lacks its gateway turn journal')
        return None, None
    turn = json.loads(path.read_text())
    if (turn['request_sha256'] != digest(turn['request']) or turn['deadline_unix'] != deadline
            or turn['run'] != run.name or turn['max_output_tokens'] != turn['request']['max_output_tokens']):
        raise ValueError('gateway turn identity changed')
    entry = entries[-1] if entries else None
    if not entry or entry['id'] != turn['id']:
        if turn['previous_id'] != (entry and entry['id']):
            raise ValueError('gateway journal and ledger disagree about the latest request')
        return turn, None
    if any(turn[key] != entry.get(key) for key in ('request_sha256', 'deadline_unix', 'counted_input', 'max_output_tokens')):
        raise ValueError('reserved request differs from its frozen intent')
    return turn, entry


def status(run, directory, deadline):
    turn, entry = load(run, directory, deadline)
    if turn is None:
        return {'phase': 'before_first_request'}
    identity = turn['id']
    response = run / f'response-{identity}.json'
    if entry is None:
        phase = 'counted_before_reservation'
    elif entry.get('state') == 'cancelled_unsent':
        phase = 'cancelled_before_send'
    elif entry.get('send_phase') == 'not_sent':
        phase = 'reserved_before_dispatch'
    elif not response.exists():
        phase = 'generation_outcome_unknown'
    elif (run / f'tool-{identity}.json').exists():
        phase = 'tool_receipt_saved'
    elif (run / f'action-{identity}.json').exists():
        phase = 'tool_outcome_unknown'
    else:
        phase = 'response_saved'
    return {'phase': phase, 'local_request_id': identity, 'request_sha256': turn['request_sha256']}


def settle_saved(run, directory, turn):
    identity = turn['id']
    response = json.loads((run / f'response-{identity}.json').read_text())
    campaign.settle(directory, identity, response)
    return response


def apply_tool(run, turn, response, call, dispatch):
    identity = turn['id']
    receipt = run / f'tool-{identity}.json'
    action = run / f'action-{identity}.json'
    binding = {'request_id': identity, 'response_id': response['id'], 'call_id': call['call_id'],
               'name': call['name'], 'arguments_sha256': digest(call['arguments'])}
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['action'] != binding:
            raise ValueError('tool receipt differs from saved response')
        return saved['result']
    if action.exists():
        raise UnresolvedAction('previous dispatch has no durable result; inspect the last completed tag')
    atomic_json(action, binding)
    try:
        result = dispatch(run, call['name'], json.loads(call['arguments']))
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        if isinstance(error, TimeoutError):
            raise
        result = {'error': str(error)[:2000]}
    atomic_json(receipt, {'name': call['name'], 'result': result, 'action': binding})
    return result


class UnresolvedAction(RuntimeError):
    pass
