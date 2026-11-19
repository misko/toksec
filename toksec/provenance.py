"""Record the framework checkout separately from a submitted server's Git commit."""
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import uuid

from toksec.stages import identifier

ROOT = Path(__file__).resolve().parents[1]


def checkout(require_clean=False, root=ROOT):
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Toksec provenance requires a Git checkout with a committed HEAD')
        return result.stdout.strip()
    commit = git('rev-parse', '--verify', 'HEAD')
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError('invalid Toksec Git commit')
    dirty = bool(git('status', '--porcelain', '--untracked-files=normal'))
    if require_clean and dirty:
        raise ValueError('Commit framework changes before preparing a measured run; the Toksec working tree is dirty')
    return {'toksec_commit': commit, 'toksec_dirty': dirty}


def run_name(stage, language, commit):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'{identifier(stage)}__{language}__{stamp}__{commit[:12]}__{uuid.uuid4().hex[:8]}'


def validate_run_id(value, stage=None, language=None, commit=None):
    """Validate a persisted identity without deriving one from a movable path."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('invalid run_id')
    if stage is not None:
        match = re.fullmatch(r'stage-(\d{2})__(cpp|rust)__(\d{8}T\d{6}Z)__([0-9a-f]{12})__([0-9a-f]{8})', value)
        if (not match or int(match[1]) != stage or match[2] != language
                or not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit)
                or match[4] != commit[:12]):
            raise ValueError('run_id does not match stage, language or Toksec commit')
    return value


def run_identity(run, manifest):
    """Old runs retain their basename; new runs retain their manifest identity."""
    if 'run_id' in manifest:
        from toksec.stages import number
        return validate_run_id(manifest['run_id'], number(manifest),
                               manifest.get('language', 'rust'), manifest.get('toksec_commit'))
    return validate_run_id(Path(run).name)
