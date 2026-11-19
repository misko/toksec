"""Standalone compile, public conformance and optional performance measurement."""
import json
import hashlib
import os
import subprocess
from toksec.artifacts import artifact_contract, validate_source
from pathlib import Path
from toksec.stages import number as stage_number
from toksec.storage import atomic_json
from toksec.provenance import checkout
from toksec import sandbox
from toksec.specification import workloads, fingerprint


def evaluate(source, directory, level, performance=False, language='rust'):
    if level == 10:
        return evaluate_counted_source(source, directory, performance, language)
    provenance = checkout()
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    artifact=directory/'candidate'
    result={**provenance, 'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(), 'framework':fingerprint(), 'stage':level,'language':language,'build':sandbox.build(Path(source).read_text(),artifact,level,language=language)}
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


def exit_code(result, performance=False):
    if not result.get('checks', {}).get('passed'):
        return 2
    if result.get('diagnostic_errors'):
        return 1
    if result.get('coverage') == 'partial' or result.get('final_grade_eligible') is False:
        return 4
    if performance and (not result.get('benchmarks') or not all(
            value.get('eligible') is True and value.get('failures') == 0
            for value in result['benchmarks'].values())):
        return 3
    return 0


def resume(source, directory, level, language='rust'):
    """Resume only completed independent API checks/workloads, never model calls."""
    directory = Path(directory)
    result = json.loads((directory/'result.json').read_text())
    if (result.get('framework') != fingerprint() or stage_number(result) != level
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


def evaluate_counted_source(source, directory, performance=False, language='rust', cpus=None):
    from toksec.specification import counted_fingerprint
    from toksec.sandbox import cgroup
    from toksec.stages import module as stage_module
    api = stage_module(10, 'api')
    benchmark = stage_module(10, 'performance')
    provenance = checkout()
    source = Path(source)
    text = validate_source(source.read_text(), artifact_contract(10, language))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    cpus = list(cpus or sorted(os.sched_getaffinity(0))[:1])
    artifact = directory / 'candidate'
    result = {**provenance, 'stage': 10, 'language': language, 'coverage': 'partial',
              'final_grade_eligible': False, 'framework': counted_fingerprint(),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'build': cgroup.build(text, artifact, language=language),
              'checks': {'passed': False, 'cases': []},
              'performance_scope': 'provisional_diagnostics_only'}
    if result['build']['passed']:
        result['checks'] = api.evaluate(artifact, directory / 'api-checks', mode='api', cpus=cpus)
    passed = result['build']['passed'] and result['checks']['passed']
    result['grading'] = {'api_passed': passed, 'full_api_passed': False,
                         'coverage': 'partial', 'performance_credit': 0,
                         'performance_status': 'not_requested' if passed else 'failed_api'}
    atomic_json(directory / 'result.json', result)
    if performance and passed:
        result['benchmarks'] = {}
        result['grading']['performance_status'] = 'provisional'
        for tls in (False, True):
            for clients in (256, 4096):
                workload = f'{"https" if tls else "http"}-4096-{clients}'
                try:
                    measurement = benchmark.measure(artifact, directory / 'diagnostics' / workload,
                                                    clients, tls, cpus)
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    measurement = {'error': str(error)[:2000]}
                    result.setdefault('diagnostic_errors', []).append(workload)
                measurement.update(eligible=False, provisional=True,
                                   scope='uncalibrated_single_round_development_diagnostic')
                result['benchmarks'][workload] = measurement
                atomic_json(directory / 'result.json', result)
    elif performance:
        result['benchmark_skipped'] = 'Failed implemented API checks prevent diagnostic performance measurement.'
    result['limitations'] = ['The independent Stage 10 API suite is incomplete.',
                            'Performance diagnostics are provisional and earn no final performance credit.']
    atomic_json(directory / 'result.json', result)
    return result
