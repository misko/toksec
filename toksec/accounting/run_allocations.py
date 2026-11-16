"""Reserve a Stage 10 run inside the shared campaign before any model request."""
from contextlib import closing
import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import fcntl
import hashlib
import sqlite3
import json
from pathlib import Path
import resource
import shutil
import time
import uuid

from toksec import campaign, metering
from toksec.artifacts import read_artifact
from toksec.specification import fingerprint
from toksec.storage import atomic_json
from toksec.provenance import checkout, run_name
from toksec.stages import number as stage_number
from toksec.accounting.counted_requests import BudgetLedger, MODEL, PRICES

BACKEND = 'stage10-counted-v1'
NANODOLLARS = Decimal(1_000_000_000)
MAX_BUDGET = Decimal('5.00')
# Settlement charges every input at cache-write price, with no cache discounts.
MIN_TOKEN_DEBIT = min(PRICES['cache_write'], PRICES['output'])
MIN_RUN_BUDGET = Decimal('0.08768')


def _money(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError('Stage 10 budget must be a decimal amount') from error
    if not amount.is_finite() or amount <= 0 or amount * NANODOLLARS != int(amount * NANODOLLARS):
        raise ValueError('Stage 10 budget must be positive with nanodollar precision')
    return amount


def _parent_available(directory):
    ledger = campaign.read(directory)
    balance = metering.totals(ledger)
    eligible = (ledger['state'] == 'active' and ledger['service_tier'] == 'default'
                and ledger['fingerprint'] == fingerprint()
                and not any(entry['state'] != 'settled' for entry in ledger['requests']))
    available = min(MAX_BUDGET, Decimal(balance['remaining_usd']),
                    Decimal(balance['remaining']) * MIN_TOKEN_DEBIT / NANODOLLARS)
    available = max(Decimal(0), available.quantize(Decimal('0.000000001'), rounding=ROUND_FLOOR))
    return ledger, balance, eligible, available


def status(directory):
    ledger, balance, eligible, available = _parent_available(directory)
    return {**balance, 'model': MODEL, 'stage': 10, 'service_tier': 'default',
            'state': ledger['state'], 'reason': ledger['reason'],
            'can_start_model_call': eligible and available >= MIN_RUN_BUDGET,
            'maximum_stage10_allocation_usd': str(available),
            'has_pending_allocation': any(e.get('allocation_kind') == BACKEND and e['state'] != 'settled'
                                          for e in ledger['requests']),
            'allocation_policy': 'Whole child-run budget reserved before launch; unused allocation released only after reconciled completion.',
            'dollar_limit': ledger['dollar_limit'], 'token_limit': ledger['token_limit'],
            'scope': ledger['scope']}


def prepare(campaign_dir, language='rust', wall_seconds=7200, model=MODEL,
            spend_target_usd=None):
    from toksec import controller
    if model != MODEL:
        raise ValueError('Stage 10 counted-request profile currently supports only gpt-6.1-terra')
    if language not in ('cpp', 'rust'):
        raise ValueError('unsupported Stage 10 language')
    if type(wall_seconds) is not int or not 120 <= wall_seconds <= 7200:
        raise ValueError('wall_seconds must be between 120 and 7200')
    campaign_dir = Path(campaign_dir).resolve()
    with campaign.locked(campaign_dir):
        ledger, _, eligible, maximum = _parent_available(campaign_dir)
        if not eligible:
            raise ValueError('campaign is unavailable or has unresolved reservations')
        amount = min(Decimal('2.00'), maximum) if spend_target_usd is None else _money(spend_target_usd)
        if amount < MIN_RUN_BUDGET or amount > maximum:
            raise ValueError(f'Stage 10 allocation must be between {MIN_RUN_BUDGET} and {maximum} USD')
        provenance = checkout(require_clean=True)
        run = campaign_dir / 'runs' / run_name(10, language, provenance['toksec_commit'])
        result = controller.counted_prepare(run, language=language, wall_seconds=wall_seconds, budget=str(amount), run_id=run.name)
        manifest = controller.read(run, 'manifest.json')
        manifest.update(campaign=str(campaign_dir), stage=10, campaign_backend=BACKEND,
                        campaign_fingerprint=ledger['fingerprint'],
                        builder_evaluation_scope='visible_smoke_only',
                        campaign_allocation_usd=str(amount), campaign_total_cap_usd=ledger['dollar_limit'])
        atomic_json(run / 'manifest.json', manifest)
    return {**result, 'stage': 10, 'campaign': str(campaign_dir),
            'allocation_usd': str(amount), 'allocation_reserved': False,
            'launch_packet': str(run / 'launch-packet.md'),
            'api_coverage': 'partial', 'performance_scope': 'provisional'}


def _validate(run):
    from toksec import controller
    run = Path(run).resolve()
    manifest = controller.read(run, 'manifest.json')
    if (stage_number(manifest) != 10
            or manifest.get('campaign_backend') != BACKEND
            or manifest.get('model') != MODEL or manifest.get('service_tier') != 'default'
            or manifest.get('reasoning_effort') != 'medium'):
        raise ValueError('invalid Stage 10 campaign profile')
    directory = Path(manifest['campaign']).resolve()
    if run.parent != directory / 'runs':
        raise ValueError('Stage 10 run must belong to its campaign runs directory')
    amount = _money(manifest['campaign_allocation_usd'])
    if amount > MAX_BUDGET or amount != _money(manifest['budget_usd']):
        raise ValueError('child budget differs from campaign allocation')
    if manifest['framework'] != controller.counted_fingerprint() or manifest['campaign_fingerprint'] != fingerprint():
        raise ValueError('framework changed since preparation; prepare a fresh run')
    read_artifact(run, 10, manifest['language'], manifest.get('artifact_sha256'))
    if not (run / 'budget.sqlite').is_file():
        raise ValueError('Stage 10 child ledger is missing')
    return manifest, directory, amount


def preflight(run):
    from toksec import controller
    reasons = []
    try:
        manifest, directory, amount = _validate(run)
        state = controller.read(run)
        child = BudgetLedger(Path(run) / 'budget.sqlite', limit_usd=manifest['budget_usd']).report()
        parent, _, eligible, maximum = _parent_available(directory)
        if not eligible or amount > maximum:
            reasons.append('Campaign cannot reserve this prepared Stage 10 allocation.')
        if manifest['started_unix'] is not None or state['finished'] or child['requests']:
            reasons.append('Run already started or child ledger is not fresh; automatic resume is disabled.')
        if any(entry.get('run') == Path(run).name for entry in parent['requests']):
            reasons.append('Campaign already contains an allocation for this run.')
        compiler = 'g++' if manifest['language'] == 'cpp' else 'rustc'
        for command in (compiler, 'gcc', 'bwrap', 'nsenter', 'systemd-run', 'systemctl', 'openssl', 'readelf', 'nm'):
            if not shutil.which(command):
                reasons.append(command + ' is unavailable.')
        if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < 16384:
            reasons.append('Descriptor hard limit must be at least 16384.')
        from toksec.accounting import counted_requests as budget
        price_date = getattr(budget, 'PRICE_DATE', metering.PRICE_DATE)
        age = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.date.fromisoformat(price_date)).days
        if not 0 <= age <= 7:
            reasons.append('Pinned Stage 10 pricing requires review before launch.')
    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error) as error:
        reasons.append(str(error))
    return {'launch_allowed': not reasons, 'reasons': reasons, 'model': MODEL,
            'service_tier': 'default', 'api_coverage': 'partial',
            'performance_scope': 'provisional', 'credentials_checked': False,
            'model_access_verified': False}


def _reserve(run, directory, amount):
    with campaign.locked(directory):
        ledger, _, eligible, maximum = _parent_available(directory)
        if not eligible or amount > maximum:
            raise ValueError('campaign cannot fund the Stage 10 allocation')
        if any(entry.get('run') == run.name for entry in ledger['requests']):
            raise ValueError('Stage 10 run already has a campaign allocation')
        identity = uuid.uuid4().hex
        reserved_tokens = int(amount * NANODOLLARS) // MIN_TOKEN_DEBIT
        ledger['requests'].append({'id': identity, 'run': run.name, 'state': 'reserved',
                                   'allocation_kind': BACKEND, 'model': MODEL,
                                   'reserved_usd': str(amount), 'reserved_tokens': reserved_tokens,
                                   'reserved_unix': time.time()})
        atomic_json(directory / 'ledger.json', ledger)
    return identity


def _reconcile(run, directory, identity, amount):
    """Unknown or inconsistent child evidence retains the entire parent hold."""
    with campaign.locked(directory):
        ledger = campaign.read(directory)
        entry = next(item for item in ledger['requests'] if item['id'] == identity)
        try:
            database = run / 'budget.sqlite'
            if not database.is_file():
                raise ValueError('Stage 10 child ledger disappeared')
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as check:
                if check.execute('SELECT COUNT(*) FROM config').fetchone()[0] != 1:
                    raise ValueError('Stage 10 child ledger configuration is missing')
                check.execute('SELECT COUNT(*) FROM requests').fetchone()
            report = BudgetLedger(database, limit_usd=str(amount)).report()
            if report['blocked'] or report['held_nanodollars'] or any(r['status'] != 'settled' for r in report['requests']):
                raise ValueError('Stage 10 child has uncertain or pending usage')
            usage = {'input': 0, 'output': 0, 'cached_input': 0, 'cache_write': 0, 'reasoning': 0}
            debit = 0
            for request in report['requests']:
                values = json.loads(request['usage'])
                inputs, outputs = metering.tokens(values['input_tokens']), metering.tokens(values['output_tokens'])
                expected = inputs * PRICES['cache_write'] + outputs * PRICES['output']
                if expected != request['debit_nanodollars']:
                    raise ValueError('Stage 10 child debit does not match usage')
                usage['input'] += inputs
                usage['output'] += outputs
                reasoning = metering.tokens((values.get('output_tokens_details') or {}).get('reasoning_tokens', 0))
                details = values.get('input_tokens_details') or {}
                cached = metering.tokens(details.get('cached_tokens', 0))
                written = metering.tokens(details.get('cache_write_tokens', 0))
                if reasoning > outputs or cached + written > inputs:
                    raise ValueError('Stage 10 child usage details exceed totals')
                usage['reasoning'] += reasoning
                usage['cached_input'] += cached
                usage['cache_write'] += written
                debit += expected
            usage['total'] = usage['input'] + usage['output']
            usage['cost_usd_upper_bound'] = str(Decimal(debit) / NANODOLLARS)
            if (debit != report['spent_nanodollars'] or Decimal(debit) > amount * NANODOLLARS
                    or usage['total'] > entry['reserved_tokens']):
                raise ValueError('Stage 10 usage exceeds campaign allocation')
            entry.update(state='settled', usage=usage, settled_unix=time.time(),
                         child_request_count=len(report['requests']),
                         child_ledger_sha256=hashlib.sha256((run / 'budget.sqlite').read_bytes()).hexdigest())
        except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error) as error:
            entry['allocation_error'] = str(error)
            ledger.update(state='uncertain', reason='Unreconciled Stage 10 allocation: ' + str(error))
            atomic_json(directory / 'ledger.json', ledger)
            return False
        atomic_json(directory / 'ledger.json', ledger)
    return True


def run_loop(run, client):
    from toksec import controller
    run = Path(run).resolve()
    manifest, directory, amount = _validate(run)
    with campaign.locked(directory, owner=True), (run / 'run.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready = preflight(run)
        if not ready['launch_allowed']:
            raise ValueError('; '.join(ready['reasons']))
        identity = _reserve(run, directory, amount)
        try:
            manifest['campaign_allocation_id'] = identity
            atomic_json(run / 'manifest.json', manifest)
            from toksec.execution.counted import _locked_run_loop
            result = _locked_run_loop(run, client)
        finally:
            _reconcile(run, directory, identity, amount)
    return {**result, 'campaign_accounting': status(directory)}
