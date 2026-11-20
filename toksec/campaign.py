import contextlib
import fcntl
import hashlib
import json
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from toksec import metering
from toksec.storage import atomic_json
from toksec.specification import fingerprint

RESERVED_TOKENS = metering.MODEL_CONTEXT_LIMIT + metering.MAX_OUTPUT
RESERVED_USD = (Decimal(metering.MODEL_CONTEXT_LIMIT) * Decimal(metering.RATES['write_upper']) * 2
                + Decimal(metering.MAX_OUTPUT) * Decimal(metering.RATES['output']) * Decimal('1.5')) / 1_000_000


TERRA = 'gpt-6.1-terra'
TERRA_RATES = {'input': '1.00', 'cached': '0.05', 'write_upper': '1.25', 'output': '5.00'}


def profile(model=metering.MODEL, request_profile="legacy"):
    if request_profile not in ("legacy", "bounded-32k"):
        raise ValueError("unknown request profile")
    if request_profile == "bounded-32k" and model != TERRA:
        raise ValueError("bounded requests require Terra")
    input_limit = 32000 if request_profile == "bounded-32k" else metering.MODEL_CONTEXT_LIMIT
    if model not in (metering.MODEL, TERRA):
        raise ValueError('unsupported metered model')
    rates = TERRA_RATES if model == TERRA else metering.RATES
    reserve_usd = (Decimal(input_limit) * Decimal(rates['write_upper']) * 2
                   + Decimal(metering.MAX_OUTPUT) * Decimal(rates['output']) * Decimal('1.5')) / 1_000_000
    return {'model': model, 'rates': rates, 'reservation_usd': str(reserve_usd),
            'request_profile': request_profile, 'input_limit': input_limit, 'output_limit': metering.MAX_OUTPUT,
            'reserved_tokens': input_limit + metering.MAX_OUTPUT,
            'price_source': 'https://developers.openai.com/api/docs/models/' + model,
            'price_verified_date': metering.PRICE_DATE,
            'prompt_cache_options': {'mode': 'implicit', 'ttl': '30m'} if model == TERRA else None}


def read(directory):
    return json.loads((Path(directory) / 'ledger.json').read_text())


@contextlib.contextmanager
def locked(directory, owner=False):
    directory = Path(directory)
    with (directory / ('.owner.lock' if owner else '.ledger.lock')).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if owner else 0))
        yield


def initialize(directory, budget_usd=None, *, import_ledger=None, request_profile="legacy"):
    profile(TERRA, request_profile)
    if import_ledger is not None and request_profile != "legacy":
        raise ValueError("cannot change historical request policy during import")
    directory = Path(directory).resolve()
    if import_ledger is not None:
        if budget_usd is not None:
            raise ValueError('choose a fresh budget or a historical ledger, not both')
        source = Path(import_ledger).resolve()
        body = source.read_bytes()
        ledger = json.loads(body)
        try:
            budget = Decimal(str(ledger['dollar_limit']))
            if not budget.is_finite() or budget <= 0:
                raise ValueError('historical budget must be positive and finite')
            if type(ledger['token_limit']) is not int or ledger['token_limit'] <= 0:
                raise ValueError('historical token limit must be a positive integer')
            if ledger['service_tier'] != 'default':
                raise ValueError('historical ledger must use standard service')
            if not isinstance(ledger['requests'], list):
                raise ValueError('historical requests must be a list')
            for entry in ledger['requests']:
                if not isinstance(entry['id'], str) or not entry['id']:
                    raise ValueError('historical request ID is required')
                if entry['state'] != 'settled':
                    raise ValueError('historical ledger has unresolved charges')
                metering.tokens(entry['usage']['total'])
                cost = Decimal(str(entry['usage']['cost_usd_upper_bound']))
                if not cost.is_finite() or cost < 0:
                    raise ValueError('historical charges must be nonnegative and finite')
        except (KeyError, TypeError, InvalidOperation) as error:
            raise ValueError('invalid historical ledger') from error
        ledger.update(imported_ledger_sha256=hashlib.sha256(body).hexdigest(),
                      imported_ledger_path=str(source),
                      scope='Measured API calls including imported history; excludes framework preparation')
        for entry in ledger['requests']:
            entry.setdefault('run', 'historical-import')
    else:
        budget = Decimal(str(budget_usd if budget_usd is not None else '3'))
        if not budget.is_finite() or budget <= 0:
            raise ValueError('budget must be positive and finite')
        selected = profile(TERRA if request_profile == 'bounded-32k' else metering.MODEL, request_profile)
        ledger = {'requests': [], 'dollar_limit': str(budget),
                  'model': selected['model'], 'token_limit': metering.TOKEN_LIMIT,
                  'service_tier': 'default', 'rates_usd_per_million': selected['rates'],
                  'price_source': selected['price_source'], 'price_verified_date': selected['price_verified_date'],
                  'scope': 'Fresh measured API campaign; excludes framework preparation'}
    if request_profile != 'legacy':
        ledger['request_profile'] = request_profile
    ledger.update(schema_version=2, state='active', reason=None, fingerprint=fingerprint(),
                  created_unix=time.time())
    metering.totals(ledger)
    directory.mkdir(parents=True, exist_ok=False)
    atomic_json(directory / 'ledger.json', ledger)
    (directory / 'runs').mkdir()
    return status(directory, TERRA if ledger.get('request_profile') == 'bounded-32k' else metering.MODEL)


def status(directory, model=None):
    ledger = read(directory)
    model = model or (TERRA if ledger.get('request_profile') == 'bounded-32k' else metering.MODEL)
    selected = profile(model, ledger.get('request_profile', 'legacy'))
    reservation = Decimal(selected['reservation_usd'])
    balance = metering.totals(ledger)
    pending = any(r['state'] == 'reserved' for r in ledger['requests'])
    eligible = (ledger['state'] == 'active' and not pending and ledger['fingerprint'] == fingerprint()
                and balance['remaining'] >= selected['reserved_tokens'] and Decimal(balance['remaining_usd']) >= reservation)
    return {**balance, 'model': model, 'service_tier': ledger['service_tier'],
            'state': ledger['state'], 'reason': ledger['reason'], 'can_start_model_call': eligible,
            'next_call_reservation_tokens': selected['reserved_tokens'], 'next_call_reservation_usd': str(reservation),
            'dollar_limit': ledger['dollar_limit'], 'token_limit': ledger['token_limit'], 'scope': ledger['scope']}


def upgrade(directory):
    with locked(directory, owner=True), locked(directory):
        ledger = read(directory)
        if ledger['state'] != 'active' or any(r['state'] == 'reserved' for r in ledger['requests']):
            raise ValueError('reconcile campaign state and pending usage before a framework upgrade')
        current = fingerprint()
        if ledger['fingerprint'] != current:
            ledger.setdefault('framework_upgrades', []).append({'previous': ledger['fingerprint'],
                         'next': current, 'unix': time.time(), 'balance': metering.totals(ledger)})
            ledger['fingerprint'] = current
            atomic_json(Path(directory) / 'ledger.json', ledger)
    return status(directory, TERRA if ledger.get('request_profile') == 'bounded-32k' else metering.MODEL)


def reserve(directory, run_id, counted_input, model=metering.MODEL, *, intent=None):
    selected = profile(model, read(directory).get('request_profile', 'legacy'))
    if type(counted_input) is not int or not 0 <= counted_input <= min(metering.MAX_INPUT, selected['input_limit']):
        raise ValueError('counted input exceeds the supported request context budget')
    with locked(directory):
        if not status(directory, model)['can_start_model_call']:
            raise ValueError('campaign cannot admit another request; inspect status')
        ledger = read(directory)
        identity = intent['id'] if intent is not None else uuid.uuid4().hex
        if any(r['id'] == identity for r in ledger['requests']):
            raise ValueError('request was already admitted')
        ledger['requests'].append({'id': identity, 'run': run_id, 'state': 'reserved',
                                   'counted_input': counted_input, 'reserved_tokens': selected['reserved_tokens'],
                                   'profile': selected, 'reserved_usd': selected['reservation_usd'], 'reserved_unix': time.time(),
                                   **({k: intent[k] for k in ('request_sha256', 'deadline_unix', 'max_output_tokens')} if intent else {}),
                                   **({'send_phase': 'not_sent'} if intent else {})})
        atomic_json(Path(directory) / 'ledger.json', ledger)
        return identity


def begin_send(directory, identity, *, cancel=False):
    """The runner crosses the generation network boundary only after this write."""
    with locked(directory):
        ledger = read(directory)
        entry = next(r for r in ledger['requests'] if r['id'] == identity)
        if entry['state'] != 'reserved' or entry.get('send_phase') != 'not_sent':
            raise ValueError('reservation was already dispatched or closed')
        if cancel:
            entry.update(state='cancelled_unsent', ended_unix=time.time())
        else:
            if ledger['state'] != 'active':
                raise ValueError('campaign is blocked')
            entry.update(send_phase='dispatch_started', dispatch_unix=time.time())
        atomic_json(Path(directory) / 'ledger.json', ledger)


def settle(directory, identity, response):
    with locked(directory):
        ledger = read(directory)
        entry = next(r for r in ledger['requests'] if r['id'] == identity)
        try:
            selected = entry.get('profile', profile())
            if entry.get('send_phase') == 'not_sent':
                raise ValueError('cannot settle an undispatched reservation')
            usage = metering.usage_record(response['usage'], selected['rates'])
            if response['model'] != selected['model'] or response['service_tier'] != 'default':
                raise ValueError('unexpected model or service tier')
            if not isinstance(response['id'], str) or not response['id'] or response['status'] not in ('completed', 'incomplete'):
                raise ValueError('a terminal response with an ID is required')
            response_digest = hashlib.sha256(json.dumps(response, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if entry['state'] == 'settled':
                if (entry['response_id'] == response['id'] and entry['usage'] == usage
                        and entry.get('response_sha256', response_digest) == response_digest):
                    return usage
                raise ValueError('conflicting settlement')
            if ('request_sha256' in entry and selected['request_profile'] == 'bounded-32k'
                    and usage['input'] != entry['counted_input']):
                raise ValueError('provider input usage differs from verified input count')
            if any(r.get('response_id') == response['id'] for r in ledger['requests']):
                raise ValueError('response already settled')
            if (usage['input'] > selected.get('input_limit', metering.MODEL_CONTEXT_LIMIT) or usage['output'] > selected.get('output_limit', metering.MAX_OUTPUT)
                    or usage['total'] > entry['reserved_tokens']
                    or Decimal(usage['cost_usd_upper_bound']) > Decimal(entry['reserved_usd'])):
                raise ValueError('usage exceeds reservation')
            entry.update(state='settled', response_id=response['id'], response_sha256=response_digest, usage=usage,
                         response_status=response['status'], settled_unix=time.time())
            if response['status'] != 'completed' or usage['input'] > metering.MAX_INPUT:
                ledger.update(state='stopped', reason='incomplete response or actual input above context budget')
        except (KeyError, TypeError, ValueError) as error:
            ledger.update(state='uncertain', reason=str(error))
            atomic_json(Path(directory) / 'ledger.json', ledger)
            raise ValueError('unreconciled usage; campaign blocked') from error
        atomic_json(Path(directory) / 'ledger.json', ledger)
        return usage
