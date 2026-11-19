"""Relocate historical publications without rewriting their evaluation evidence."""
from pathlib import Path
import fcntl
import shutil
import tempfile

from toksec.provenance import validate_run_id
from toksec.result_storage import destination, digest, files, read, verify, _update_index
from toksec.storage import atomic_json

MAPPING = 'provenance/run-id-migration.json'
ORIGINALS = 'provenance/run-id-migration/original'


def historical_identity(record):
    explicit = [record[key] for key in ('run_id', 'raw_run_id') if record.get(key)]
    if explicit and len(set(explicit)) != 1:
        raise ValueError('conflicting historical raw run IDs')
    identity = explicit[0] if explicit else Path(record.get('source_run', '')).name
    if not identity:
        raise ValueError('historical result has no recorded raw run ID')
    return validate_run_id(identity)


def verify_relocation(target):
    target = Path(target)
    mapping = read(target / MAPPING)
    actual = files(target)
    record = read(target / 'run.json')
    if destination(target.parent, record) != target:
        raise ValueError('relocation directory does not match identity')
    if mapping.get('run_id') != record.get('run_id'):
        raise ValueError('relocation identity mismatch')
    for name, entry in mapping['files'].items():
        path = Path(entry['path'])
        if path.is_absolute() or '..' in path.parts or actual.get(str(path)) != entry['sha256']:
            raise ValueError('relocated artifact changed: ' + name)
    return mapping


def _stage(source, target, identity, source_path):
    before = files(source)
    shutil.copytree(source, target)
    if files(target) != before:
        raise ValueError('migration copy differs from original')
    old = read(source / 'run.json')
    backup = target / ORIGINALS
    if backup.exists() or (target / MAPPING).exists():
        raise ValueError('historical result already contains relocation metadata')
    backup.mkdir(parents=True)
    moved = ('run.json', 'README.md', 'sha256.json')
    for name in moved:
        if (target / name).exists():
            shutil.copy2(target / name, backup / name)
    aliases = {old['id']} if old.get('id') else set()
    for path in (target / 'evaluation').glob('*/evaluation.json'):
        value = read(path).get('run_id')
        if value:
            aliases.add(value)
    aliases.discard(identity)
    record = dict(old, id=identity, run_id=identity, raw_run_id=identity, path=identity,
                  publication_version=2, persisted_run_id=False,
                  historical_ids=sorted(aliases), historical_path=source_path,
                  run_id_provenance='Recorded historical raw run ID; original inputs and reports are unchanged')
    destination(target.parent, record)
    atomic_json(target / 'run.json', record)
    (target / 'README.md').write_text(
        f'# Stage {record["stage"]} / {record["language"]}\n\n'
        f'Run: `{identity}`. Status: **{record.get("status", "unknown")}**.\n\n'
        'The submitted source and Git history are in [implementation/](implementation/).\n'
        'Original reports and figures are in [evaluation/](evaluation/).\n'
        'Instructions and accounting are in `inputs/` and `accounting/`.\n\n'
        f'This historical publication moved from `{source_path}`. '
        'Its reports, figures, inputs and implementation are unchanged. '
        'No server tests were rerun and no missing framework commit was inferred.\n\n'
        'Original publication metadata is in [provenance/run-id-migration/original/](provenance/run-id-migration/original/). '
        'The [checksum mapping](provenance/run-id-migration.json) accounts for every original file. '
        'Historical evaluation run IDs are retained as aliases in `run.json`.\n')
    mapping = {'schema_version': 1, 'run_id': identity, 'source_path': source_path,
               'historical_ids': sorted(aliases),
               'files': {name: {'path': f'{ORIGINALS}/{name}' if name in moved else name,
                                'sha256': expected} for name, expected in before.items()}}
    atomic_json(target / MAPPING, mapping)
    (target / 'sha256.json').unlink()
    atomic_json(target / 'sha256.json', files(target))
    verify(target)
    verify_relocation(target)
    return mapping


def migrate_run_ids(results, apply=False):
    """Validate the whole batch before installation; interrupted moves can resume."""
    results = Path(results).absolute()
    if not results.is_dir() or any(p.is_symlink() for p in (results, *results.parents)):
        raise ValueError('results must be an existing nonsymlink directory')
    with (results / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pending, seen, report = [], set(), []
        for path in sorted(results.glob('stage-*/*/run.json')):
            record = read(path)
            if destination(results, record) != path.parent or record.get('layout_version') != 1:
                raise ValueError('normalize the historical snapshot layout before relocating it')
            verify(path.parent)
            identity = historical_identity(record)
            if identity in seen:
                raise ValueError('historical run ID collision: ' + identity)
            seen.add(identity)
            dest = results / identity
            if dest.is_symlink():
                raise ValueError('symlinked migration destination')
            before = files(path.parent)
            relative = str(path.parent.relative_to(results))
            if dest.exists():
                verify(dest)
                mapping = verify_relocation(dest)
                expected = {name: entry['sha256'] for name, entry in mapping['files'].items()}
                if mapping['source_path'] != relative or expected != before:
                    raise ValueError('migration destination collision: ' + identity)
            pending.append((path.parent, dest, before, relative))
            report.append({'source': relative, 'destination': identity, 'run_id': identity,
                           'files': len(before), 'status': 'migrated' if apply else 'planned'})
        for path in sorted(results.glob('*/provenance/run-id-migration.json')):
            target = path.parent.parent
            if target.name in seen:
                continue
            verify(target)
            mapping = verify_relocation(target)
            report.append({'source': mapping['source_path'], 'destination': target.name,
                           'run_id': mapping['run_id'], 'files': len(mapping['files']),
                           'status': 'already_migrated'})
        if not pending:
            if apply and report:
                _update_index(results)
            return report
        with tempfile.TemporaryDirectory(prefix='.run-id-migration-', dir=results) as tmp:
            staged = []
            for source, dest, before, relative in pending:
                if dest.exists():
                    continue
                target = Path(tmp) / dest.name
                _stage(source, target, dest.name, relative)
                staged.append((target, dest))
            if not apply:
                return report
            archive = results / 'provenance/run-id-migration'
            if archive.is_symlink() or archive.parent.is_symlink():
                raise ValueError('symlinked index archive')
            archive.mkdir(parents=True, exist_ok=True)
            for name in ('index.json', 'README.md'):
                if (results / name).is_symlink() or (archive / name).is_symlink():
                    raise ValueError('symlinked index metadata')
                if (results / name).is_file() and not (archive / name).exists():
                    shutil.copy2(results / name, archive / name)
            for target, dest in staged:
                target.rename(dest)
            # Do not remove any source until every installed copy verifies.
            for source, dest, before, _ in pending:
                verify(dest)
                verify_relocation(dest)
                if files(source) != before:
                    raise ValueError('historical source changed during migration')
            for source, _, _, _ in pending:
                shutil.rmtree(source)
                if not any(source.parent.iterdir()):
                    source.parent.rmdir()
            _update_index(results)
        return report
