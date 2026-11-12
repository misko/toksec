import contextlib
import fcntl
import hashlib
import json
import time
import uuid
from decimal import Decimal
from pathlib import Path

import metering
from controller import atomic_json
from toksec.specification import ROOT, fingerprint

PILOT = ROOT / 'results/2026-11-11-luna-http-l1-pilot/ledger.json'
RESERVED_TOKENS = metering.MODEL_CONTEXT_LIMIT + metering.MAX_OUTPUT
RESERVED_USD = (Decimal(metering.MODEL_CONTEXT_LIMIT) * Decimal(metering.RATES['write_upper']) * 2
                + Decimal(metering.MAX_OUTPUT) * Decimal(metering.RATES['output']) * Decimal('1.5')) / 1_000_000


TERRA = 'gpt-6.1-terra'
TERRA_RATES = {'input': '1.00', 'cached': '0.05', 'write_upper': '1.25', 'output': '5.00'}


def profile(model=metering.MODEL):
    if model not in (metering.MODEL, TERRA):
        raise ValueError('unsupported metered model')
    rates = TERRA_RATES if model == TERRA else metering.RATES
    reserve_usd = (Decimal(metering.MODEL_CONTEXT_LIMIT) * Decimal(rates['write_upper']) * 2
                   + Decimal(metering.MAX_OUTPUT) * Decimal(rates['output']) * Decimal('1.5')) / 1_000_000
    return {'model': model, 'rates': rates, 'reservation_usd': str(reserve_usd),
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


def initialize(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    ledger = json.loads(PILOT.read_text())
    if any(r['state'] != 'settled' for r in ledger['requests']):
        raise ValueError('pilot has unresolved charges')
    ledger.update(schema_version=2, state='active', reason=None, fingerprint=fingerprint(),
                  imported_ledger_sha256=hashlib.sha256(PILOT.read_bytes()).hexdigest(),
                  scope='Measured Luna API calls, including recorded pilot; excludes unmetered framework preparation',
                  created_unix=time.time())
    for entry in ledger['requests']:
        entry['run'] = 'historical-python-pilot'
    atomic_json(directory / 'ledger.json', ledger)
    (directory / 'runs').mkdir()
    return status(directory)


def status(directory, model=metering.MODEL):
    selected = profile(model)
    reservation = Decimal(selected['reservation_usd'])
    ledger = read(directory)
    balance = metering.totals(ledger)
    pending = any(r['state'] == 'reserved' for r in ledger['requests'])
    eligible = (ledger['state'] == 'active' and not pending and ledger['fingerprint'] == fingerprint()
                and balance['remaining'] >= RESERVED_TOKENS and Decimal(balance['remaining_usd']) >= reservation)
    return {**balance, 'model': model, 'service_tier': ledger['service_tier'],
            'state': ledger['state'], 'reason': ledger['reason'], 'can_start_model_call': eligible,
            'next_call_reservation_tokens': RESERVED_TOKENS, 'next_call_reservation_usd': str(reservation),
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
    return status(directory)


def reserve(directory, run_id, counted_input, model=metering.MODEL):
    selected = profile(model)
    if type(counted_input) is not int or not 0 <= counted_input <= metering.MAX_INPUT:
        raise ValueError('counted input exceeds the supported 64000-token context budget')
    with locked(directory):
        if not status(directory, model)['can_start_model_call']:
            raise ValueError('campaign cannot admit another request; inspect status')
        ledger = read(directory)
        identity = uuid.uuid4().hex
        ledger['requests'].append({'id': identity, 'run': run_id, 'state': 'reserved',
                                   'counted_input': counted_input, 'reserved_tokens': RESERVED_TOKENS,
                                   'profile': selected, 'reserved_usd': selected['reservation_usd'], 'reserved_unix': time.time()})
        atomic_json(Path(directory) / 'ledger.json', ledger)
        return identity


def settle(directory, identity, response):
    with locked(directory):
        ledger = read(directory)
        entry = next(r for r in ledger['requests'] if r['id'] == identity)
        try:
            selected = entry.get('profile', profile())
            usage = metering.usage_record(response['usage'], selected['rates'])
            if entry['state'] == 'settled':
                if entry['response_id'] == response['id'] and entry['usage'] == usage:
                    return usage
                raise ValueError('conflicting settlement')
            if response['model'] != selected['model'] or response['service_tier'] != 'default':
                raise ValueError('unexpected model or service tier')
            if any(r.get('response_id') == response['id'] for r in ledger['requests']):
                raise ValueError('response already settled')
            if (usage['input'] > metering.MODEL_CONTEXT_LIMIT or usage['output'] > metering.MAX_OUTPUT
                    or usage['total'] > entry['reserved_tokens']
                    or Decimal(usage['cost_usd_upper_bound']) > Decimal(entry['reserved_usd'])):
                raise ValueError('usage exceeds reservation')
            entry.update(state='settled', response_id=response['id'], usage=usage,
                         response_status=response['status'], settled_unix=time.time())
            if response['status'] != 'completed' or usage['input'] > metering.MAX_INPUT:
                ledger.update(state='stopped', reason='incomplete response or actual input above context budget')
        except (KeyError, TypeError, ValueError) as error:
            ledger.update(state='uncertain', reason=str(error))
            atomic_json(Path(directory) / 'ledger.json', ledger)
            raise ValueError('unreconciled usage; campaign blocked') from error
        atomic_json(Path(directory) / 'ledger.json', ledger)
        return usage
