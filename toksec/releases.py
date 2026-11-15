"""Append-only Git releases, operated through a private sandbox."""
import hashlib
import json
import re
import subprocess
import tempfile
import time
import uuid
from toksec.storage import atomic_json
from toksec.provenance import run_identity
from toksec.specification import counted_fingerprint
from pathlib import Path

from toksec.stages import number as stage_number
from toksec import sandbox, controller, evaluate
from toksec.artifacts import read_artifact, validate_source
from toksec.stage_dispatch import stage_of, stage10_tool

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
    if stage_of(run) == 10:
        return stage10_tool(run, 'init_repository', {})
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
    if stage_of(run) == 10:
        return stage10_tool(run, 'release_candidate', {'note': note})
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
    contract=read_artifact(run, stage_number(manifest), manifest.get('language', 'rust'), manifest.get('artifact_sha256'))
    filename=contract['submission']['source_file']
    source=(candidate/filename).read_bytes()
    validate_source(source.decode('utf-8'), contract)
    digest=hashlib.sha256(source).hexdigest()
    if existing and existing[-1]['source_sha256']==digest:
        return existing[-1]
    number=int(existing[-1]['tag'].split('/')[1])+1 if existing else 1
    if number>999999:
        raise ValueError('release sequence exhausted')
    tag=f'release/{number:06d}'
    metadata={'candidate':identity,'stage':stage_number(manifest),'language':manifest.get('language', 'rust'),'note':note,
              'source_sha256':digest,'passed_checks':sorted(passed),
              'evaluation_scope':manifest['builder_evaluation_scope'], 'smoke_passed':report['checks']['passed'],'framework':manifest['fingerprint'],
              'recorded_unix':time.time(), 'capacity':controller.capacity(run), 'artifact_sha256':manifest.get('artifact_sha256')}
    repository=run/'repository'
    (repository/filename).write_bytes(source)
    (repository/'release.json').write_text(json.dumps(metadata,indent=2)+'\n')
    git(run,'add','--',filename,'release.json')
    git(run,'commit','--allow-empty','-m',note)
    commit=git(run,'rev-parse','HEAD').strip()
    git(run,'tag',tag,commit)
    return {'tag':tag,'commit':commit,**metadata}


def grade(run, output=None, performance=False):
    import uuid
    from toksec.evaluation_artifacts import write_evaluation
    run = Path(run)
    output = Path(output) if output is not None else run / 'evaluation' / uuid.uuid4().hex
    if output.resolve().is_relative_to((run / 'repository').resolve()):
        raise ValueError('parent evaluation output cannot be inside the implementation repository')
    if stage_of(run) == 10:
        return counted_grade(run, output, performance)
    records=list_releases(run)
    if not records:
        raise ValueError('no tagged release to grade')
    release=records[-1]
    from toksec.specification import fingerprint
    if release['framework'] != fingerprint():
        raise ValueError('release uses a different evaluator; grade with its original framework checkout')
    manifest=controller.read(run, 'manifest.json')
    contract=read_artifact(run, stage_number(release), release.get('language', 'rust'), manifest.get('artifact_sha256'))
    filename=contract['submission']['source_file']
    source=git(run,'show',release['tag']+':'+filename)
    validate_source(source, contract)
    if hashlib.sha256(source.encode()).hexdigest()!=release['source_sha256']:
        raise ValueError('tagged source hash differs from release metadata')
    with tempfile.TemporaryDirectory(prefix='toksec-grade-') as temporary:
        file=Path(temporary)/filename
        file.write_text(source)
        result=evaluate.evaluate(file,output,stage_number(release),performance,language=release.get('language', 'rust'))
    result['run_toksec_commit'] = manifest.get('toksec_commit')
    result['release']=release
    from toksec.storage import atomic_json
    atomic_json(Path(output)/'result.json',result)
    write_evaluation(output, run_id=run_identity(run, manifest),
                     release={k: release[k] for k in ('tag', 'commit', 'source_sha256')},
                     contract_sha256=manifest.get('artifact_sha256'), evaluator_sha256=fingerprint(),
                     environment={k: manifest[k] for k in ('compiler', 'platform', 'cpu_affinity', 'toolchain') if k in manifest},
                     coverage='full', result=result)
    return result


def counted_release(run, note, initialize=False):
    run = Path(run); state = controller.read(run); m = controller.read(run, 'manifest.json')
    if not state['latest']:
        raise ValueError('submit working source before release')
    artifact = run / 'candidates' / state['latest']; report = controller.read(artifact, 'report.json')
    checks = {case['id'] for case in report['checks'].get('cases', []) if case['passed']}
    if not report['build']['passed'] or 'bootstrap' not in checks:
        raise ValueError('release must compile and pass bootstrap')
    if state['tags'] and not set(state['tags'][-1]['passed_checks']) <= checks:
        raise ValueError('release would lose previously passing visible checks')
    if not (run / 'repository/.git').exists():
        if not initialize:
            raise ValueError('call init_repository first')
        git(run, 'init', '--initial-branch=main')
    contract = read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    source_name = contract['submission']['source_file']
    source = (artifact / source_name).read_bytes(); digest = hashlib.sha256(source).hexdigest()
    validate_source(source.decode('utf-8'), contract)
    if state['tags'] and state['tags'][-1]['source_sha256'] == digest:
        return state['tags'][-1]
    meta = {'tag': f'release/{len(state["tags"])+1:06d}', 'source_sha256': digest,
            'candidate': state['latest'], 'passed_checks': sorted(checks), 'note': note[:2000],
            'recorded_unix': time.time(), 'capacity': controller.counted_capacity(run), 'scope': 'visible_smoke_only',
            'artifact_sha256': m.get('artifact_sha256')}
    (run / 'repository' / source_name).write_bytes(source)
    atomic_json(run / 'repository/release.json', meta)
    git(run, 'add', source_name, 'release.json'); git(run, 'commit', '-m', meta['tag'])
    git(run, 'tag', meta['tag'])
    state['tags'].append(meta); atomic_json(run / 'state.json', state)
    return meta


def counted_final_export(run):
    run = Path(run); m, state = controller.read(run, 'manifest.json'), controller.read(run)
    result = {'capacity': controller.counted_capacity(run), 'release_count': len(state['tags']), 'final_grade_eligible': False,
              'coverage': 'partial', 'performance_scope': 'provisional'}
    if state['tags']:
        tag = state['tags'][-1]; name = 'main.cpp' if m['language'] == 'cpp' else 'main.rs'
        source = git(run, 'show', tag['tag'] + ':' + name)
        if hashlib.sha256(source.encode()).hexdigest() != tag['source_sha256']:
            raise ValueError('tag source identity mismatch')
        (run / 'final').mkdir(exist_ok=True); (run / 'final' / name).write_text(source)
        result['last_tag'] = tag
        result['source'] = str(run / 'final' / name)
    else:
        result['no_submission'] = 'No completed working release tag'
    atomic_json(run / 'result.json', result)
    return result


def counted_grade(run, output=None, performance=False):
    import tempfile
    from toksec.evaluate import evaluate_counted_source
    from toksec.evaluation_artifacts import write_evaluation
    run = Path(run)
    output = Path(output) if output is not None else run / 'evaluation' / uuid.uuid4().hex
    if output.resolve().is_relative_to((run / 'repository').resolve()):
        raise ValueError('parent evaluation output cannot be inside the implementation repository')
    m, state = controller.read(run, 'manifest.json'), controller.read(run)
    if not state['tags']:
        raise ValueError('no tagged submission')
    tag = state['tags'][-1]
    contract = read_artifact(run, 10, m['language'], m.get('artifact_sha256'))
    name = contract['submission']['source_file']
    source = git(run, 'show', tag['tag'] + ':' + name)
    validate_source(source, contract)
    if hashlib.sha256(source.encode()).hexdigest() != tag['source_sha256']:
        raise ValueError('tag digest mismatch')
    release = {'tag': tag['tag'], 'commit': git(run, 'rev-parse', tag['tag'] + '^{commit}').strip(),
               'source_sha256': tag['source_sha256']}
    with tempfile.TemporaryDirectory(prefix='toksec-stage10-grade-') as temporary:
        source_path = Path(temporary) / name
        source_path.write_text(source)
        result = evaluate_counted_source(source_path, output, performance, m['language'], cpus=m['cpus'])
    result['run_toksec_commit'] = m.get('toksec_commit')
    result['release'] = release
    atomic_json(output / 'result.json', result)
    write_evaluation(output, run_id=run_identity(run, m), release=release,
                     contract_sha256=m.get('artifact_sha256'), evaluator_sha256=counted_fingerprint(),
                     environment={k: m[k] for k in ('toolchain', 'openssl_version', 'cpus') if k in m},
                     coverage='partial', result=result)
    return result
