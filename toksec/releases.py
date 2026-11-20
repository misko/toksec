"""Append-only Git releases, operated through a private sandbox."""
import hashlib
import json
import os
import platform
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
    records = []
    for tag in tags:
        commit = git(run, 'rev-parse', tag + '^{commit}').strip()
        metadata = json.loads(git(run, 'show', commit + ':release.json'))
        if metadata.get('tag', tag) != tag or metadata.get('commit', commit) != commit:
            raise ValueError('release metadata differs from Git tag or commit')
        records.append({**metadata, 'tag': tag, 'commit': commit})
    return records


def latest_identity(run):
    if not (Path(run) / 'repository/.git').is_dir():
        return None
    ref = git(run, 'for-each-ref', '--sort=-refname', '--count=1',
              '--format=%(refname:short)', 'refs/tags/release/').strip()
    if not ref:
        return None
    if not TAG.fullmatch(ref):
        raise ValueError('invalid latest release tag')
    commit = git(run, 'rev-parse', ref + '^{commit}').strip()
    meta = json.loads(git(run, 'show', commit + ':release.json'))
    return {'tag': ref, 'commit': commit, 'source_sha256': meta['source_sha256']}


def initialize(run, note='Initial working snapshot'):
    if stage_of(run) == 10:
        return stage10_tool(run, 'init_repository', {})
    controller.validate(run)
    if controller.read(run)['finished']:
        raise ValueError('run is finished')
    if not (Path(run)/'repository'/'.git').is_dir():
        git(run,'init','--initial-branch=main')
    existing=list_releases(run)
    if existing:
        return {**existing[-1], 'publication': 'already_published'}
    return publish(run, note)


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
        return {**existing[-1], 'publication': 'already_published'}
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
    return {'tag':tag,'commit':commit,**metadata,'publication':'published'}


def grade_environment(run, manifest, *, comparison=False, calibration=None):
    from toksec.evaluation_artifacts import digest
    from toksec.specification import fingerprint, specification

    stage = stage_number(manifest)
    language = manifest.get('language', 'rust')
    current = specification(stage, language)
    original = controller.read(run, 'specification.json')
    evaluator = fingerprint()
    if manifest['fingerprint'] != evaluator and not comparison:
        raise ValueError('release uses a different evaluator; grade with its original framework checkout or select comparison grading')
    if comparison:
        if not controller.read(run)['finished']:
            raise ValueError('comparison grading requires a finished builder')
        if not manifest.get('artifact_sha256'):
            raise ValueError('comparison grading requires the original artifact contract hash')
        if original != current:
            raise ValueError('stage specification changed; this evaluator cannot regrade the original contract as a comparable series')

    compiler = current['build']['compiler']
    environment = {
        'mode': 'comparison' if comparison else 'original',
        'builder_framework': manifest['fingerprint'], 'evaluator_framework': evaluator,
        'specification_sha256': digest(original), 'workloads': current['benchmarks'],
        'compiler': subprocess.check_output([compiler, '--version'], text=True).strip(),
        'toolchain': str(sandbox.toolchain()) if language == 'rust' else '/usr/bin/g++',
        'hostname': platform.node(), 'platform': platform.platform(), 'kernel': platform.release(),
        'cpu_affinity': sorted(os.sched_getaffinity(0)), 'calibration': None,
    }
    if calibration is not None:
        from toksec.gateway_calibration import environment as calibration_environment, measurement_fingerprint
        actual_host = calibration_environment()
        raw = Path(calibration).read_bytes()
        record = json.loads(raw)
        expected = {w['id']: w for w in current['benchmarks']}
        observed = record.get('workloads', {})
        cells = record.get('cells', {})
        if (not record.get('calibration_id') or record.get('status') != 'completed' or
                record.get('stage') != stage or not isinstance(observed, dict) or not observed or
                not isinstance(cells, dict) or set(observed) != set(cells) or
                any(not isinstance(cell, dict) or type(cell.get('qualified')) is not bool
                    or not isinstance(cell.get('reasons'), list) for cell in cells.values()) or
                any(expected.get(key) != value for key, value in observed.items()) or
                record.get('measurement_fingerprint') != measurement_fingerprint(stage) or
                record.get('environment') != actual_host):
            raise ValueError('calibration does not match stage, workload definitions or host CPU affinity')
        environment['calibration_environment'] = actual_host
        environment['calibration'] = {
            'id': record['calibration_id'], 'sha256': hashlib.sha256(raw).hexdigest(),
            'measurement_fingerprint': record['measurement_fingerprint'],
            'cells': {key: {'qualified': value['qualified'], 'reasons': value['reasons']}
                      for key, value in record['cells'].items()},
        }
    return environment


def grade(run, output=None, performance=False, *, tag=None, comparison=False,
          calibration=None, resume=False):
    from toksec.evaluation_artifacts import write_evaluation
    run = Path(run)
    output = Path(output) if output is not None else run / 'evaluation' / uuid.uuid4().hex
    if output.resolve().is_relative_to((run / 'repository').resolve()):
        raise ValueError('parent evaluation output cannot be inside the implementation repository')
    if stage_of(run) == 10:
        if tag is not None or comparison or calibration:
            raise ValueError('exact-tag comparison grading currently supports the regular HTTP runner; Stage 10 grading is provisional')
        return counted_grade(run, output, performance)
    if tag is not None and not TAG.fullmatch(tag):
        raise ValueError('tag must be a numbered release/NNNNNN')
    records = list_releases(run)
    if not records:
        raise ValueError('no tagged release to grade')
    release = records[-1] if tag is None else next((r for r in records if r['tag'] == tag), None)
    if release is None:
        raise ValueError(f'no completed release named {tag}')
    manifest = controller.read(run, 'manifest.json')
    identity = run_identity(run, manifest)
    stage = stage_number(manifest)
    language = manifest.get('language', 'rust')
    if (release['framework'] != manifest['fingerprint'] or stage_number(release) != stage or
            release.get('language', 'rust') != language):
        raise ValueError('release identity differs from frozen run manifest')
    contract_hash = manifest.get('artifact_sha256')
    if release.get('artifact_sha256', contract_hash) != contract_hash:
        raise ValueError('release artifact digest differs from frozen run manifest')
    environment = grade_environment(run, manifest, comparison=comparison, calibration=calibration)
    contract = read_artifact(run, stage, language, contract_hash)
    filename = contract['submission']['source_file']
    source = git(run, 'show', release['commit'] + ':' + filename)
    validate_source(source, contract)
    if hashlib.sha256(source.encode()).hexdigest() != release['source_sha256']:
        raise ValueError('tagged source hash differs from release metadata')
    with tempfile.TemporaryDirectory(prefix='toksec-grade-') as temporary:
        file = Path(temporary) / filename
        file.write_text(source)
        if resume and (output / 'result.json').exists():
            result = controller.read(output, 'result.json')
            if (result['framework'] != environment['evaluator_framework'] or
                    result['source_sha256'] != release['source_sha256'] or
                    stage_number(result) != stage or result['language'] != language):
                raise ValueError('partial result differs from requested evaluator, stage or source')
            if performance and result.get('checks', {}).get('passed'):
                result = evaluate.resume(file, output, stage, language)
        else:
            result = evaluate.evaluate(file, output, stage, performance, language=language)
    calibration_record = environment['calibration']
    if calibration_record:
        for key, cell in result.get('benchmarks', {}).items():
            control = calibration_record['cells'].get(key, {'qualified': False, 'reasons': ['no calibration cell']})
            cell.update(calibration_qualified=control['qualified'], calibration_reasons=control['reasons'])
    elif comparison and performance and 11 <= stage <= 16:
        for cell in result.get('benchmarks', {}).values():
            cell.update(calibration_qualified=False, calibration_reasons=['matching calibration unavailable'])
    if result.get('benchmarks') and evaluate.exit_code(result, performance=True) != 0:
        result['grading'].update(performance_status='invalid_measurement', performance_credit=0)
    result['run_toksec_commit'] = manifest.get('toksec_commit')
    result['release'] = release
    atomic_json(output / 'result.json', result)
    write_evaluation(output, run_id=identity, release=release,
                     contract_sha256=contract_hash, evaluator_sha256=environment['evaluator_framework'],
                     environment=environment, coverage='full', result=result)
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
