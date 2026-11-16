"""Publish immutable implementation evidence separately from parent evaluations."""
from datetime import datetime, timezone
import fcntl
import ctypes
import os
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from toksec.stages import number as stage_number
from toksec.storage import atomic_json
from toksec.provenance import run_identity, validate_run_id

LAYOUT_VERSION = 1


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_evaluation_envelopes(root):
    evaluations = Path(root) / 'evaluation'
    if not evaluations.exists():
        return
    for directory in evaluations.iterdir():
        if directory.is_dir() and (directory / 'report.md').exists() and not (directory / 'evaluation.json').is_file():
            raise ValueError(
                f'unregistered evaluation report: {directory}; missing evaluation.json. '
                'For security reports, use scripts/record_security_evaluation.py against '
                'the raw run, then scripts/publish_results.py. Preserve the report before reconciliation.')


def files(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('symlinked artifact directory')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlinked artifact: ' + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path)
        elif not path.is_dir():
            raise ValueError('nonregular artifact: ' + str(path))
    return result


def destination(results, record):
    stage, language = record.get('stage'), record.get('language')
    if type(stage) is not int or not 1 <= stage <= 10 or language not in ('cpp', 'rust'):
        raise ValueError('invalid stage or language')
    if record.get('publication_version') == 2:
        identity = validate_run_id(record.get('run_id'))
        if record.get('persisted_run_id'):
            validate_run_id(identity, stage, language, record.get('toksec_commit'))
        if any(record.get(key) != identity for key in ('id', 'raw_run_id', 'path')):
            raise ValueError('inconsistent run identity')
        result = Path(results) / identity
    else:
        result = Path(results) / f'stage-{stage:02d}' / language
    for p in (result, *result.parents):
        if p.is_symlink():
            raise ValueError('symlinked publication path')
    return result


def mapped(name, evaluation_id, security_paths=frozenset()):
    path = Path(name)
    if name.startswith('evaluation/'):
        parts = path.parts
        if len(parts) == 3 and parts[2] in ('evaluation.json', 'api.json', 'performance.json', 'report.md'):
            return name
        if len(parts) >= 4 and parts[2] == 'figures' and path.suffix in ('.png', '.svg', '.csv', '.json'):
            return name
        if name in security_paths:
            return name
        raise ValueError('unclassified parent evaluation artifact: ' + name)
    if name in ('run.json', 'README.md', 'sha256.json'):
        return 'provenance/legacy/' + name
    if name in ('manifest.json', 'specification.json', 'launch-packet.md', 'artifact.json'):
        return 'inputs/' + name
    if name.startswith('builder-inputs/'):
        return 'inputs/builder-inputs/' + name[len('builder-inputs/'):]
    if name.startswith('attempts/'):
        if path.name in ('manifest.json', 'launch-packet.md'):
            return 'inputs/' + name
        if path.name in ('completion.json', 'ledger.json'):
            return 'accounting/' + name
    if name == 'ledger.json':
        return 'accounting/ledger.json'
    if name == 'implementation.bundle' or name == 'releases.json':
        return 'implementation/' + name
    if name in ('main.cpp', 'main.rs'):
        return 'implementation/source/' + name
    if re.fullmatch(r'release-\d{6}\.(cpp|rs)', name):
        return 'implementation/releases/' + name
    if name in ('state.json', 'progress.md', 'model-report.md') or re.fullmatch(r'release-\d{6}-smoke.json', name):
        return 'implementation/evidence/' + name
    if (name in ('timeline.json', 'metrics.csv', 'grade-summary.json')
            or re.fullmatch(r'release-\d{6}-evaluation.json', name)):
        return 'evaluation/' + evaluation_id + '/raw/' + name
    if path.suffix in ('.png', '.svg') and path.name == name:
        return 'evaluation/' + evaluation_id + '/figures/' + name
    raise ValueError('unclassified published artifact: ' + name)


def _release(snapshot, record):
    releases = []
    if (snapshot / 'releases.json').exists():
        releases = read(snapshot / 'releases.json').get('releases', [])
    elif (snapshot / 'timeline.json').exists():
        releases = read(snapshot / 'timeline.json').get('releases', [])
    last = releases[-1] if releases else {}
    tag = last.get('tag', record.get('last_tag'))
    source_hash = last.get('source_sha256')
    if not source_hash and tag:
        source = snapshot / (tag.replace('/', '-') + ('.cpp' if record['language'] == 'cpp' else '.rs'))
        if source.exists():
            source_hash = digest(source)
    commit = last.get('commit')
    if tag and not re.fullmatch(r'release/\d{6}', tag):
        raise ValueError('invalid release tag')
    if tag:
        source = snapshot / (tag.replace('/', '-') + ('.cpp' if record['language'] == 'cpp' else '.rs'))
        if source.exists():
            actual_hash = digest(source)
            if source_hash is not None and source_hash != actual_hash:
                raise ValueError('release metadata source hash mismatch')
            source_hash = actual_hash
    if tag and (snapshot / 'implementation.bundle').exists():
        with tempfile.TemporaryDirectory(prefix='toksec-bundle-verify-') as tmp:
            repository = Path(tmp) / 'repository'
            subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--quiet', '--bare',
                            str(snapshot / 'implementation.bundle'), str(repository)], check=True, capture_output=True)
            actual_commit = subprocess.check_output(['git','-C',str(repository),'rev-parse',tag+'^{commit}'],text=True).strip()
            body = subprocess.check_output(['git','-C',str(repository),'show',tag+':'+('main.cpp' if record['language']=='cpp' else 'main.rs')])
            actual_hash = hashlib.sha256(body).hexdigest()
            if commit is not None and commit != actual_commit:
                raise ValueError('release metadata commit mismatch')
            if source_hash is not None and source_hash != actual_hash:
                raise ValueError('bundle source differs from archived source')
            commit, source_hash = actual_commit, actual_hash
    final_source = snapshot / ('main.cpp' if record['language'] == 'cpp' else 'main.rs')
    if source_hash is not None and final_source.exists() and digest(final_source) != source_hash:
        raise ValueError('final source differs from tagged source')
    return {'tag': tag, 'commit': commit, 'source_sha256': source_hash}, releases


def transform(snapshot, target):
    """Copy a legacy snapshot, preserving every original file byte and its mapping."""
    snapshot, target = Path(snapshot), Path(target)
    before = files(snapshot)
    security_paths = set()
    for envelope in (snapshot / 'evaluation').glob('*/evaluation.json'):
        data = read(envelope)
        if data.get('kind') == 'security':
            from toksec.security_evaluations import verify_security_files
            names = verify_security_files(envelope.parent, data)
            security_paths.update(str(envelope.parent.relative_to(snapshot) / name) for name in names)
    record = read(snapshot / 'run.json')
    destination(target.parent, record)  # validate trusted identity fields
    if record.get('layout_version') == LAYOUT_VERSION:
        shutil.copytree(snapshot, target)
        verify(target)
        return record
    target.mkdir()
    snapshot_hash = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    evaluation_id = 'imported-' + snapshot_hash[:16]
    mapping = {}
    for name, expected in before.items():
        dest = mapped(name, evaluation_id, security_paths)
        output = target / dest
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot / name, output)
        if digest(output) != expected:
            raise ValueError('copy hash mismatch: ' + name)
        mapping[name] = {'path': dest, 'sha256': expected}
    from toksec.artifacts import artifact_contract
    artifact_path = 'inputs/artifact.json' if (target / 'inputs/artifact.json').exists() else 'provenance/artifact.json'
    if artifact_path.startswith('provenance/'):
        atomic_json(target / artifact_path, artifact_contract(record['stage'], record['language']))
    release, releases = _release(snapshot, record)
    if not (target / 'implementation/releases.json').exists():
        (target / 'implementation').mkdir(exist_ok=True)
        atomic_json(target / 'implementation/releases.json', {'releases': releases})
    source_name = 'main.cpp' if record['language'] == 'cpp' else 'main.rs'
    if release['tag'] and not (target / 'implementation/source' / source_name).exists():
        source = snapshot / (release['tag'].replace('/', '-') + Path(source_name).suffix)
        if source.exists():
            (target / 'implementation/source').mkdir(exist_ok=True)
            shutil.copyfile(source, target / 'implementation/source' / source_name)
    raw = None
    if (snapshot / 'grade-summary.json').exists():
        raw = read(snapshot / 'grade-summary.json')
    elif release['tag']:
        path = snapshot / (release['tag'].replace('/', '-') + '-evaluation.json')
        if path.exists():
            raw = read(path)
    if raw is not None:
        claimed_hash = raw.get('source_sha256', raw.get('release', {}).get('source_sha256'))
        claimed_framework = raw.get('framework', raw.get('release', {}).get('framework'))
        if claimed_hash is not None and claimed_hash != release['source_sha256']:
            raise ValueError('evaluation source hash differs from tagged source')
        if claimed_framework is not None and claimed_framework != record.get('framework'):
            raise ValueError('evaluation framework differs from run')
    coverage = 'partial' if record['stage'] == 10 and raw else 'full' if raw else 'unknown'
    from toksec.evaluation_artifacts import write_evaluation
    eval_dir = target / 'evaluation' / evaluation_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    write_evaluation(eval_dir, run_id=record.get('id', record.get('source_run', 'unknown')),
                     release=release, contract_sha256=digest(snapshot / 'artifact.json') if (snapshot / 'artifact.json').exists() else None, evaluator_sha256=record.get('framework'),
                     environment={'provenance': 'Imported historical evidence; no tests rerun during migration'},
                     coverage=coverage, result=raw, performance=(raw or {}).get('benchmarks'))
    canonical = sorted((target / 'evaluation').glob('*/evaluation.json'))
    canonical = [p for p in canonical if p.parent.name != evaluation_id]
    latest_evaluation = str(max(canonical, key=lambda p: p.stat().st_mtime_ns).parent.relative_to(target)) if canonical else 'evaluation/' + evaluation_id
    record = dict(record, layout_version=LAYOUT_VERSION,
                  paths={'inputs': 'inputs', 'artifact_contract': artifact_path, 'implementation': 'implementation', 'accounting': 'accounting',
                         'evaluation': 'evaluation', 'latest_evaluation': latest_evaluation},
                  artifact_contract_provenance='reconstructed_for_storage' if 'artifact.json' not in before else 'supplied_to_builder')
    atomic_json(target / 'run.json', record)
    atomic_json(target / 'migration.json', {'layout_version': LAYOUT_VERSION, 'source_snapshot_sha256': snapshot_hash,
                                         'files': mapping})
    (target / 'README.md').write_text(
        f'# Stage {record["stage"]} — {record["language"]}\n\n'
        f'Run: `{record.get("id", "unknown")}`. Status: **{record.get("status", "unknown")}**.\n\n'
        'The frozen submission and Git bundle are in [implementation/](implementation/).\n'
        f'Parent reports and figures are in [evaluation/]({latest_evaluation}/report.md).\n'
        'Supplied instructions are in `inputs/`; spending evidence is in `accounting/`.\n'
        'Migration preserved the original evidence without running new tests.\n'
        'See `run.json` for protocol identity and `migration.json` for byte-preservation mappings.\n')
    atomic_json(target / 'sha256.json', files(target))
    verify(target)
    return record


def _security_contract(target, envelope):
    for candidate in (target / 'inputs/artifact.json', envelope / 'artifact.json'):
        if candidate.is_file():
            return candidate
    raise ValueError('security evaluation contract is missing')


def verify(target):
    target = Path(target)
    require_evaluation_envelopes(target)
    current = files(target)
    for name, expected in read(target / 'sha256.json').items():
        if current.get(name) != expected:
            raise ValueError('published file hash mismatch: ' + name)
    for entry in read(target / 'migration.json')['files'].values():
        if current.get(entry['path']) != entry['sha256']:
            raise ValueError('migrated artifact changed: ' + entry['path'])
    for envelope in (target / 'evaluation').glob('*/evaluation.json'):
        data = read(envelope)
        if data.get('kind') == 'security':
            from toksec.security_evaluations import verify_security_files
            verify_security_files(envelope.parent, data)
            run = read(target / 'run.json')
            releases = read(target / 'implementation/releases.json')['releases']
            expected = next((r for r in releases if r.get('tag') == data['release']['tag']), None)
            if (data['run_id'] != run.get('run_id', run['id']) or expected is None
                    or any(data['release'][key] != expected.get(key)
                           for key in ('commit', 'source_sha256'))
                    or data['contract_sha256'] != digest(_security_contract(target, envelope.parent))):
                raise ValueError('security evaluation does not match published release')
    return current


def install(staging, dest):
    """Atomically exchange complete directories on the Linux sandbox host."""
    staging, dest = Path(staging), Path(dest)
    if not dest.exists():
        staging.rename(dest)
        return
    if not (dest / 'run.json').is_file():
        raise ValueError('refusing to replace unmanaged directory')
    libc = ctypes.CDLL(None, use_errno=True)
    exchange = getattr(libc, 'renameat2', None)
    if exchange is None:
        raise RuntimeError('atomic directory exchange requires Linux renameat2')
    exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    exchange.restype = ctypes.c_int
    if exchange(-100, os.fsencode(staging), -100, os.fsencode(dest), 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    shutil.rmtree(staging)


def publish_snapshot(snapshot, results):
    snapshot, results = Path(snapshot).absolute(), Path(results).absolute()
    files(snapshot)
    record = read(snapshot / 'run.json')
    dest = destination(results, record)
    results.mkdir(parents=True, exist_ok=True)
    with (results / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if snapshot == dest.resolve() and record.get('layout_version') == LAYOUT_VERSION:
            verify(dest)
            return record
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.publish-', dir=dest.parent) as tmp:
            staging = Path(tmp) / 'entry'
            record = transform(snapshot, staging)
            if dest.exists() and record.get('publication_version') == 2:
                verify(dest)
                old = read(dest / 'run.json')
                for key in ('id', 'stage', 'language', 'toksec_commit', 'framework', 'started_utc'):
                    if old.get(key) != record.get(key):
                        raise ValueError('run identity collision: ' + key)
                old_inputs = files(dest / 'inputs')
                new_inputs = files(staging / 'inputs')
                # A historical migration may have preserved only a subset of the
                # prepared inputs. Re-publishing from the raw run restores the
                # missing files; every previously preserved file must match
                # byte-for-byte, and nothing preserved may disappear.
                if any(new_inputs.get(name) != expected for name, expected in old_inputs.items()):
                    raise ValueError('run identity collision: prepared inputs')
                new_implementation = files(staging / 'implementation')
                for name, expected in files(dest / 'implementation').items():
                    if old.get('status') == 'running' and name == 'releases.json':
                        continue
                    if new_implementation.get(name) != expected:
                        raise ValueError('run identity collision: implementation provenance')
            if dest.exists() and snapshot != dest.resolve() and read(dest / 'run.json').get('id') == record.get('id'):
                old_evaluations = dest / 'evaluation'
                if old_evaluations.exists():
                    files(old_evaluations)
                    for path in old_evaluations.iterdir():
                        other = staging / 'evaluation' / path.name
                        if other.exists():
                            if files(other) != files(path):
                                raise ValueError('evaluation identity collision')
                        else:
                            shutil.copytree(path, other)
                (staging / 'sha256.json').unlink()
                atomic_json(staging / 'sha256.json', files(staging))
            install(staging, dest)
        _update_index(results)
    return record


def update_index(results):
    results = Path(results).absolute()
    if results.is_symlink():
        raise ValueError('symlinked result root')
    results.mkdir(parents=True, exist_ok=True)
    with (results / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _update_index(results)


def _update_index(results):
    paths = sorted(set(results.glob('stage-*/*/run.json')) | set(results.glob('*/run.json')))
    entries = [read(p) for p in paths]
    for path, record in zip(paths, entries):
        if destination(results, record) != path.parent:
            raise ValueError('result identity does not match directory')
    def order(record):
        stamp = record.get('started_utc', '')
        try:
            started = datetime.strptime(stamp, '%Y-%m-%dT%H-%M-%SZ').replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            try:
                parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                started = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
            except ValueError:
                started = float('-inf')
        precise = record.get('started_unix')
        if type(precise) in (int, float) and math.isfinite(precise) and precise > 0:
            started = precise
        return started, record.get('id', ''), record.get('path', '')
    latest = {}
    for record in entries:
        key = (record['stage'], record['language'])
        if key not in latest or order(record) > order(latest[key]):
            latest[key] = record
    all_entries = sorted(entries, key=lambda r: (r['stage'], r['language'], order(r)))
    entries = [latest[key] for key in sorted(latest)]
    atomic_json(results / 'index.json', {'selection': 'Latest started run per stage/language, no starter and smoke-only feedback', 'runs': entries, 'all_runs': all_entries})
    rows = [f'| {r["stage"]} | {r["language"]} | {r["protocol"]} | {r["status"]} | [{r["started_utc"]}]({r["path"]}/README.md) |' for r in entries]
    (results / 'README.md').write_text('# Latest server experiments\n\nOne current run per stage and language. Protocols and budgets differ; do not pool scores.\n'
        'Implementations, inputs, accounting, and parent evaluations have separate folders.\n\n'
        '| Stage | Language | Protocol | Status | Latest run (UTC) |\n|---|---|---|---|---|\n' + '\n'.join(rows) + '\n')
    return entries


def snapshot_run(run, snapshot):
    """Collect an allowlisted flat snapshot from either runner's raw run."""
    run, snapshot = Path(run).absolute(), Path(snapshot)
    if run.is_symlink():
        raise ValueError('symlinked raw run')
    manifest, state = read(run / 'manifest.json'), read(run / 'state.json')
    for name in ('manifest.json', 'state.json', 'launch-packet.md', 'artifact.json', 'specification.json'):
        if (run / name).is_symlink():
            raise ValueError('symlinked raw input')
    stage = stage_number(manifest)
    language = manifest.get('language', 'rust')
    if (run / 'artifact.json').exists() or manifest.get('artifact_sha256'):
        from toksec.artifacts import read_artifact
        read_artifact(run, stage, language, expected_sha256=manifest.get('artifact_sha256'))
    if not manifest.get('started_unix'):
        raise ValueError('run has not started')
    if manifest.get('starter') or manifest.get('starter_candidate') or manifest.get('starter_sha256'):
        raise ValueError('starter runs are not eligible')
    if stage != 10 and manifest.get('builder_evaluation_scope') != 'visible_smoke_only':
        raise ValueError('run did not use smoke-only feedback')
    snapshot.mkdir()
    stamp = datetime.fromtimestamp(manifest['started_unix'], timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
    framework = manifest.get('framework', manifest.get('fingerprint'))
    protocol = ('toksec-' + manifest['toksec_commit'][:12] if manifest.get('toksec_commit')
                else 'stage10-experimental' if stage == 10
                else read(run / 'specification.json').get('version', 'unknown'))
    identity = run_identity(run, manifest)
    record = {'id': identity, 'publication_version': 2, 'persisted_run_id': 'run_id' in manifest,
              'stage': stage, 'language': language, 'model': manifest.get('model', 'unknown'),
              'status': 'builder_finished' if state['finished'] else 'running', 'protocol': protocol,
              'framework': framework, 'started_utc': stamp, 'started_unix': manifest['started_unix'],
              'source_run': str(run), 'run_id': identity, 'raw_run_id': identity,
              'input_policy': {'starter': False, 'feedback': 'visible_smoke_only'},
              'wall_seconds': manifest['wall_seconds'], 'path': identity,
              'comparison_policy': 'Do not pool different protocols, languages, models, budgets or input policies.'}
    if manifest.get('toksec_commit'):
        record['toksec_commit'] = manifest['toksec_commit']
    destination(snapshot.parent, record)
    for name in ('manifest.json', 'launch-packet.md', 'artifact.json', 'specification.json'):
        if (run / name).is_file():
            shutil.copyfile(run / name, snapshot / name)
    if (run / 'builder-inputs').exists():
        files(run / 'builder-inputs')
        shutil.copytree(run / 'builder-inputs', snapshot / 'builder-inputs')
    if stage == 10:
        from toksec.accounting.counted_requests import BudgetLedger
        attempts = [run]
        if manifest.get('prior_attempt'):
            attempts.insert(0, Path(manifest['prior_attempt']))
        ledgers = []
        for index, attempt in enumerate(attempts):
            am = read(attempt / 'manifest.json')
            ledger = BudgetLedger(attempt / 'budget.sqlite', limit_usd=am['budget_usd']).report()
            ledgers.append({'attempt': index + 1, 'source_run': str(attempt), 'accounting': ledger})
            dest = snapshot / 'attempts' / str(index + 1)
            dest.mkdir(parents=True)
            for name in ('manifest.json', 'launch-packet.md'):
                shutil.copyfile(attempt / name, dest / name)
        limit = manifest.get('campaign_total_cap_usd', manifest['budget_usd'])
        record['budget_usd'] = limit
        record['run_budget_usd'] = manifest['budget_usd']
        record['api_coverage'] = 'partial'
        record['performance_scope'] = 'provisional'
        if state['finished']:
            atomic_json(snapshot / 'ledger.json', {'campaign_limit_usd': limit, 'attempts': ledgers,
                        'spent_usd_upper_bound': str(sum(x['accounting']['spent_nanodollars'] for x in ledgers) / 1e9),
                        'pending_usd': sum(x['accounting']['held_nanodollars'] for x in ledgers) / 1e9,
                        'run_allocation_usd': manifest['budget_usd'],
                        'parent_campaign': read(Path(manifest['campaign']) / 'ledger.json') if manifest.get('campaign') else None,
                        'campaign_allocation_id': manifest.get('campaign_allocation_id')})
        if (run / 'grade-summary.json').exists() and state['finished']:
            shutil.copyfile(run / 'grade-summary.json', snapshot / 'grade-summary.json')
            record['status'] = 'partially_graded'
        record['inventory_management'] = 'preserved_snapshot'
    else:
        ledger = read(Path(manifest['campaign']) / 'ledger.json')
        record['budget_usd'] = ledger['dollar_limit']
        if state['finished']:
            atomic_json(snapshot / 'ledger.json', ledger)
        analyses = [p for p in run.glob('analysis*') if (p / 'timeline.json').is_file()]
        if analyses and state['finished']:
            analysis = max(analyses, key=lambda p: (p / 'timeline.json').stat().st_mtime)
            for path in analysis.iterdir():
                if path.is_file() and (path.name in ('timeline.json', 'implementation.bundle', 'metrics.csv')
                                       or path.suffix in ('.png', '.svg', '.cpp', '.rs')):
                    shutil.copyfile(path, snapshot / path.name)
                if path.is_dir() and (path / 'result.json').is_file() and 'interrupted' not in path.name:
                    shutil.copyfile(path / 'result.json', snapshot / (path.name + '-evaluation.json'))
            record['status'] = 'partially_graded'
    if state['finished']:
        for name in ('state.json', 'progress.md', 'model-report.md'):
            if (run / name).is_file():
                shutil.copyfile(run / name, snapshot / name)
        repository = run / 'repository'
        if (repository / '.git').exists():
            from toksec.releases import git
            tags = git(run, 'tag', '--list', 'release/*').splitlines()
            tags = sorted(tag for tag in tags if re.fullmatch(r'release/\d{6}', tag))
            if tags:
                subprocess.run(['git', '-C', str(repository), 'bundle', 'create', str(snapshot / 'implementation.bundle'), '--all'],
                               check=True, capture_output=True)
                releases = []
                source_name = 'main.cpp' if language == 'cpp' else 'main.rs'
                for tag in tags:
                    source = git(run, 'show', tag + ':' + source_name).encode()
                    meta = json.loads(git(run, 'show', tag + ':release.json'))
                    if hashlib.sha256(source).hexdigest() != meta['source_sha256']:
                        raise ValueError('tag source hash mismatch')
                    if 'tag' not in meta:
                        # Historical release.json predates the tag field; the sealed
                        # Git tag is authoritative and is recorded as such.
                        meta['tag'] = tag
                        meta['tag_provenance'] = 'git_tag'
                    meta['commit'] = git(run, 'rev-parse', tag + '^{commit}').strip()
                    (snapshot / (tag.replace('/', '-') + Path(source_name).suffix)).write_bytes(source)
                    releases.append(meta)
                    report = run / 'candidates' / meta['candidate'] / 'report.json'
                    if report.exists():
                        atomic_json(snapshot / (tag.replace('/', '-') + '-smoke.json'), read(report).get('checks', {}))
                atomic_json(snapshot / 'releases.json', {'releases': releases})
                record['last_tag'] = tags[-1]
    if (run / 'evaluation').exists():
        require_evaluation_envelopes(run)
        from toksec.artifacts import validate_evaluation
        release_records = {r['tag']: r for r in read(snapshot / 'releases.json')['releases']} if (snapshot / 'releases.json').exists() else {}
        # A historical packet may carry only a reconstructed contract; resolve it
        # from the evaluation envelope that recorded it.
        contract_file = run / 'artifact.json'
        for directory in sorted((run / 'evaluation').iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('invalid evaluation directory')
            if not (directory / 'evaluation.json').exists():
                continue
            data = validate_evaluation(read(directory / 'evaluation.json'))
            release = data['release']; expected = release_records.get(release['tag'])
            if (data['run_id'] != identity or expected is None
                    or any(release[key] != expected.get(key) for key in ('commit', 'source_sha256'))):
                raise ValueError('parent evaluation does not match a published release')
            selected = []
            if data.get('kind') == 'security':
                from toksec.security_evaluations import verify_security_files
                candidate = contract_file if contract_file.is_file() else directory / 'artifact.json'
                if not candidate.is_file() or data['contract_sha256'] != digest(candidate):
                    raise ValueError('security evaluation contract does not match run')
                selected = verify_security_files(directory, data)
            else:
                for name in files(directory):
                    if name in ('evaluation.json','api.json','performance.json','report.md') or (
                            name.startswith('figures/') and Path(name).suffix in ('.png','.svg','.csv','.json')):
                        selected.append(name)
            dest = snapshot / 'evaluation' / directory.name
            for name in selected:
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(directory / name, target)
    atomic_json(snapshot / 'run.json', record)
    return record


def publish_run(run, results):
    results = Path(results).absolute()
    results.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.collect-', dir=results) as tmp:
        snapshot = Path(tmp) / 'snapshot'
        snapshot_run(run, snapshot)
        record = publish_snapshot(snapshot, results)
    update_index(results)
    return record


def migrate(results, apply=False):
    results = Path(results).absolute()
    if results.is_symlink():
        raise ValueError('symlinked result root')
    planned = []
    for path in sorted(results.glob('stage-*/*/run.json')):
        record = read(path)
        expected = destination(results, record)
        if expected != path.parent:
            raise ValueError('result identity does not match directory')
        if record.get('layout_version') == LAYOUT_VERSION:
            verify(path.parent)
            planned.append({'path': str(path.parent), 'status': 'already_migrated'})
            continue
        files(path.parent)
        planned.append({'path': str(path.parent), 'status': 'migrated' if apply else 'planned'})
        if apply:
            publish_snapshot(path.parent, results)
        else:
            with tempfile.TemporaryDirectory(prefix='toksec-migration-check-') as tmp:
                transform(path.parent, Path(tmp) / 'entry')
    if apply:
        update_index(results)
    return planned
