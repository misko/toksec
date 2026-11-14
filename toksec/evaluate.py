"""Standalone compile, public conformance and optional performance measurement."""
import json
from pathlib import Path
from controller import atomic_json
from toksec import sandbox
from toksec.specification import workloads


def evaluate(source, directory, level, performance=False):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    artifact=directory/'candidate'
    result={'level':level,'build':sandbox.build(Path(source).read_text(),artifact,level)}
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
