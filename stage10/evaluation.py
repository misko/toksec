"""Stage 10 adapter for the shared source and tagged-release evaluation paths."""
import hashlib
import os
from pathlib import Path
import subprocess

from toksec.artifacts import artifact_contract, validate_source
from toksec.storage import atomic_json
from stage10 import benchmark, evaluate, sandbox


def evaluate_source(source, directory, performance=False, language='rust', cpus=None):
    from stage10.runner import identity
    source = Path(source)
    text = validate_source(source.read_text(), artifact_contract(10, language))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    cpus = list(cpus or sorted(os.sched_getaffinity(0))[:1])
    artifact = directory / 'candidate'
    result = {'level': 10, 'language': language, 'coverage': 'partial',
              'final_grade_eligible': False, 'framework': identity(),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'build': sandbox.build(text, artifact, language=language),
              'checks': {'passed': False, 'cases': []},
              'performance_scope': 'provisional_diagnostics_only'}
    if result['build']['passed']:
        result['checks'] = evaluate.evaluate(artifact, directory / 'api-checks', mode='api', cpus=cpus)
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
