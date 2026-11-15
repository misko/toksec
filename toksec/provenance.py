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
