"""Record parent security analyses without executing their evidence files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

from toksec.artifacts import read_artifact, validate_evaluation
from toksec.provenance import checkout, run_identity
from toksec.result_storage import files
from toksec.stages import number
from toksec.storage import atomic_json


def verify_security_files(directory, record):
    validate_evaluation(record)
    if record.get('kind') != 'security':
        raise ValueError('expected security evaluation')
    directory = Path(directory)
    if record['evaluation_id'] != directory.name:
        raise ValueError('security evaluation ID differs from directory')
    actual = files(directory)
    expected = {entry['path']: entry['sha256'] for entry in record['artifacts']}
    if set(actual) != set(expected) | {'evaluation.json'}:
        raise ValueError('security evaluation contains missing or unlisted files')
    for entry in record['artifacts']:
        path = directory / entry['path']
        if actual[entry['path']] != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError('security artifact checksum or size mismatch')
    return ['evaluation.json', *expected]


def record_security_evaluation(run, *, tag, analysis, report, evidence=None, figures=None,
                               evaluation_id=None):
    """Freeze a completed analysis and bind it to a tagged server submission."""
    from toksec.releases import git
    run = Path(run).resolve()
    if not re.fullmatch(r'release/[0-9]{6}', tag):
        raise ValueError('expected a release tag')
    manifest = json.loads((run / 'manifest.json').read_text())
    contract = read_artifact(run, number(manifest), manifest.get('language', 'rust'),
                             manifest.get('artifact_sha256'))
    if not (run / 'artifact.json').is_file():
        raise ValueError('security analysis requires the frozen artifact contract')
    commit = git(run, 'rev-parse', tag + '^{commit}').strip()
    source = git(run, 'show', commit + ':' + contract['submission']['source_file']).encode()
    release = json.loads(git(run, 'show', commit + ':release.json'))
    source_hash = hashlib.sha256(source).hexdigest()
    if release['tag'] != tag or release['source_sha256'] != source_hash:
        raise ValueError('release metadata does not match submitted source')
    allowed = {'evaluator_sha256', 'environment', 'status', 'scope', 'methods', 'limitations', 'findings'}
    if not isinstance(analysis, dict) or set(analysis) != allowed:
        raise ValueError('analysis must contain exactly: ' + ', '.join(sorted(allowed)))
    now = datetime.now(timezone.utc)
    identity = evaluation_id or f'security-{now.strftime("%Y%m%dT%H%M%SZ")}-{uuid.uuid4().hex[:8]}'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', identity):
        raise ValueError('invalid evaluation ID')
    report = Path(report)
    if report.is_symlink() or not report.is_file():
        raise ValueError('report must be a regular file')
    payload = {'report.md': report.read_bytes()}
    for prefix, directory in (('evidence', evidence), ('figures', figures)):
        if directory is not None:
            directory = Path(directory)
            if not directory.is_dir():
                raise ValueError(prefix + ' must be a directory')
            for name in files(directory):
                payload[prefix + '/' + name] = (directory / name).read_bytes()
    record = {'schema_version': 1, 'kind': 'security', 'evaluation_id': identity,
              'run_id': run_identity(run, manifest),
              'release': {'tag': tag, 'commit': commit, 'source_sha256': source_hash},
              'contract_sha256': hashlib.sha256((run / 'artifact.json').read_bytes()).hexdigest(),
              **checkout(), 'run_toksec_commit': manifest.get('toksec_commit'),
              'created_utc': now.isoformat(), **analysis,
              'artifacts': [{'path': name, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
                            for name, body in sorted(payload.items())]}
    validate_evaluation(record)
    json.dumps(record, allow_nan=False)
    parent = run / 'evaluation'
    if parent.is_symlink():
        raise ValueError('evaluation directory must not be a symlink')
    parent.mkdir(exist_ok=True)
    output = parent / identity
    if output.exists() or output.is_symlink():
        raise ValueError('evaluation already exists; choose a new evaluation ID')
    with tempfile.TemporaryDirectory(prefix='.security-', dir=run) as temporary:
        staging = Path(temporary) / identity
        staging.mkdir()
        for name, body in payload.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        atomic_json(staging / 'evaluation.json', record)
        verify_security_files(staging, record)
        # Serialize installation with other parent security recorders.
        import fcntl
        with (run / '.security-evaluations.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if output.exists() or output.is_symlink():
                raise ValueError('evaluation already exists; choose a new evaluation ID')
            staging.rename(output)
    return record
