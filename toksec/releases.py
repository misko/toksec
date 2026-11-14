"""Append-only Git releases, operated through a private sandbox."""
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from toksec import sandbox, controller, evaluate

TAG = re.compile(r'release/([0-9]{6})\Z')


def git(run, *args):
    repository = Path(run).resolve() / 'repository'
    repository.mkdir(exist_ok=True)
    command = sandbox.base() + ['--bind', str(repository), '/workspace', '--chdir', '/workspace',
        '--setenv', 'GIT_CONFIG_NOSYSTEM', '1', '--setenv', 'GIT_AUTHOR_NAME', 'Toksec builder',
        '--setenv', 'GIT_AUTHOR_EMAIL', 'builder@toksec.invalid', '--setenv', 'GIT_COMMITTER_NAME', 'Toksec builder',
        '--setenv', 'GIT_COMMITTER_EMAIL', 'builder@toksec.invalid', '--',
        '/usr/bin/git', '-c', 'safe.directory=/workspace', '-c', 'core.hooksPath=/dev/null', *args]
    result = subprocess.run(command, capture_output=True, timeout=20,
                            preexec_fn=sandbox.limits(512, 15), env={'PATH':'/usr/bin:/bin'})
    if result.returncode:
        raise ValueError('sandbox Git failed: ' + result.stderr.decode(errors='replace')[-2000:])
    return result.stdout.decode()


def list_releases(run):
    if not (Path(run)/'repository'/'.git').is_dir():
        return []
    tags = sorted(t for t in git(run, 'tag', '--list', 'release/*').splitlines() if TAG.fullmatch(t))
    return [{'tag':tag, 'commit':git(run,'rev-parse',tag+'^{commit}').strip(),
             **json.loads(git(run,'show',tag+':release.json'))} for tag in tags]


def initialize(run):
    controller.validate(run)
    if controller.read(run)['finished']:
        raise ValueError('run is finished')
    if not (Path(run)/'repository'/'.git').is_dir():
        git(run,'init','--initial-branch=main')
    existing=list_releases(run)
    if existing:
        return existing[-1]
    return publish(run, 'Initial working snapshot')


def publish(run, note):
    run=Path(run)
    manifest=controller.validate(run)
    state=controller.read(run)
    if state['finished']:
        raise ValueError('run is finished')
    if not isinstance(note,str) or not note.strip() or len(note)>2000:
        raise ValueError('release note must contain 1 to 2000 characters')
    if not (run/'repository'/'.git').is_dir():
        raise ValueError('call init_repository before publishing a release')
    identity=state['last']
    if not identity or identity in state.get('invalidated',[]):
        raise ValueError('latest candidate is unavailable or invalidated')
    candidate=run/'candidates'/identity
    report=controller.read(candidate,'report.json')
    passed=controller.passed(report)
    if not report['build']['passed'] or 'bootstrap' not in passed:
        raise ValueError('release must compile and pass bootstrap')
    existing=list_releases(run)
    if existing and not set(existing[-1]['passed_checks']) <= passed:
        raise ValueError('release loses previously passing public checks')
    source=(candidate/'main.rs').read_bytes()
    digest=hashlib.sha256(source).hexdigest()
    if existing and existing[-1]['source_sha256']==digest:
        return existing[-1]
    number=int(existing[-1]['tag'].split('/')[1])+1 if existing else 1
    if number>999999:
        raise ValueError('release sequence exhausted')
    tag=f'release/{number:06d}'
    metadata={'candidate':identity,'level':manifest['level'],'note':note,
              'source_sha256':digest,'passed_checks':sorted(passed),
              'full_acceptance':report['checks']['passed'],'framework':manifest['fingerprint']}
    repository=run/'repository'
    (repository/'main.rs').write_bytes(source)
    (repository/'release.json').write_text(json.dumps(metadata,indent=2)+'\n')
    git(run,'add','--','main.rs','release.json')
    git(run,'commit','--allow-empty','-m',note)
    commit=git(run,'rev-parse','HEAD').strip()
    git(run,'tag',tag,commit)
    return {'tag':tag,'commit':commit,**metadata}


def grade(run, output, performance=False):
    records=list_releases(run)
    if not records:
        raise ValueError('no tagged release to grade')
    release=records[-1]
    from toksec.specification import fingerprint
    if release['framework'] != fingerprint():
        raise ValueError('release uses a different evaluator; grade with its original framework checkout')
    source=git(run,'show',release['tag']+':main.rs')
    if hashlib.sha256(source.encode()).hexdigest()!=release['source_sha256']:
        raise ValueError('tagged source hash differs from release metadata')
    with tempfile.TemporaryDirectory(prefix='toksec-grade-') as temporary:
        file=Path(temporary)/'main.rs'
        file.write_text(source)
        result=evaluate.evaluate(file,output,release['level'],performance)
    result['release']=release
    from controller import atomic_json
    atomic_json(Path(output)/'result.json',result)
    return result
