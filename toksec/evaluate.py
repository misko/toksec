"""Standalone compile, public conformance and optional performance measurement."""
import json
import hashlib
from pathlib import Path
from toksec.storage import atomic_json
from toksec import sandbox
from toksec.specification import workloads, fingerprint


def evaluate(source, directory, level, performance=False, language='rust'):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    artifact=directory/'candidate'
    result={'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(), 'framework':fingerprint(), 'level':level,'language':language,'build':sandbox.build(Path(source).read_text(),artifact,level,language=language)}
    if result['build']['passed']:
        result['checks']=sandbox.evaluate(artifact,level)
        atomic_json(directory/'result.json',result)
        if performance and result['checks']['passed']:
            result['benchmarks']={}
            for workload in workloads(level):
                result['benchmarks'].update(sandbox.invoke_driver(artifact,level,'benchmark',workload=workload.id,rounds=workload.rounds))
                atomic_json(directory/'result.json',result)
        elif performance:
            result['benchmark_skipped']='Correctness checks must pass before performance measurement.'
    api_passed = result['build']['passed'] and result.get('checks', {}).get('passed', False)
    cases = result.get('checks', {}).get('cases', [])
    result['grading'] = {'api_passed': api_passed, 'api_checks_passed': sum(c['passed'] for c in cases),
                         'api_checks_failed': sum(not c['passed'] for c in cases),
                         'performance_status': 'measured' if 'benchmarks' in result else ('not_requested' if api_passed else 'failed_api')}
    if not api_passed:
        result['grading']['performance_credit'] = 0
        result['grading']['deduction'] = 'Failed API requirements lose API credit; all performance credit is forfeited.'
        result['benchmark_skipped'] = 'Build and all required API checks must pass before performance measurement.'
    atomic_json(directory/'result.json',result)
    return result


def resume(source, directory, level, language='rust'):
    """Resume only completed independent API checks/workloads, never model calls."""
    directory = Path(directory)
    result = json.loads((directory/'result.json').read_text())
    if (result.get('framework') != fingerprint() or result.get('level') != level
            or result.get('language') != language
            or result.get('source_sha256') != hashlib.sha256(Path(source).read_bytes()).hexdigest()):
        raise ValueError('partial evaluation does not match source/profile/framework')
    if not result.get('checks', {}).get('passed'):
        raise ValueError('partial evaluation has no successful completed API gate')
    result.setdefault('benchmarks', {})
    for workload in workloads(level):
        if workload.id not in result['benchmarks']:
            result['benchmarks'].update(sandbox.invoke_driver(directory/'candidate',level,'benchmark',workload=workload.id,rounds=workload.rounds))
            atomic_json(directory/'result.json',result)
    cases = result['checks']['cases']
    result['grading'] = {'api_passed': True, 'api_checks_passed': len(cases), 'api_checks_failed': 0, 'performance_status': 'measured'}
    atomic_json(directory/'result.json',result)
    return result
