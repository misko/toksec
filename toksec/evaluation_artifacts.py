"""Parent-owned evaluation records bound to an immutable submission."""
import hashlib
import json
from pathlib import Path

from toksec.storage import atomic_json
from toksec.artifacts import validate_evaluation
from toksec.benchmark import stage_matrix_valid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def write_evaluation(output, *, run_id, release, contract_sha256,
                     evaluator_sha256, environment, coverage, result,
                     performance=None):
    """Write derived reports without modifying the implementation or raw evidence.

    Missing historical identity is explicit. The caller owns coverage: running
    every implemented test does not mean the full declared contract is covered.
    """
    output = Path(output)
    if output.is_symlink():
        raise ValueError('evaluation directory must not be a symlink')
    release = {key: release.get(key) for key in ('tag', 'commit', 'source_sha256')}
    missing = [f'release.{key}' for key, value in release.items() if value is None]
    missing += [key for key, value in [('contract_sha256', contract_sha256),
                                      ('evaluator_sha256', evaluator_sha256)] if value is None]
    verified = not missing
    checks = result.get('checks', result) if result is not None else {}
    cases = checks.get('cases', [])
    if not isinstance(cases, list) or any(not isinstance(c, dict) or
            type(c.get('passed')) is not bool for c in cases):
        raise ValueError('invalid API case evidence')
    # Stage 10 appends orchestration failures to its case array. They affect the
    # gate, but are not additional behavioral requirements.
    behavioral = [c for c in cases if not c.get('id', '').endswith('-runtime')]
    passed = sum(c['passed'] for c in behavioral) if result is not None else None
    total = len(behavioral) if result is not None else None
    build_failed = result is not None and result.get('build', {}).get('passed') is False
    if result is None:
        api_status = 'not_run'
    elif build_failed or checks.get('passed') is False or any(not c['passed'] for c in cases):
        api_status = 'failed'
    elif checks.get('passed') is True and cases:
        api_status = 'passed'
    else:
        api_status = 'error'
    measurements = performance if performance is not None else (result or {}).get('benchmarks')
    perf = {'status': 'not_run', 'credit': None, 'metrics': None}
    if result is None:
        pass
    elif api_status == 'failed':
        perf.update(status='skipped_api_failure', credit=0)
    elif (coverage == 'partial' and api_status == 'passed' and measurements
          and (result or {}).get('performance_scope') == 'provisional_diagnostics_only'):
        perf.update(status='provisional', credit=0,
                    metrics={name: dict(value, eligible=False, provisional=True)
                             for name, value in measurements.items()})
    elif coverage != 'full':
        perf.update(status='skipped_incomplete_suite', credit=0)
    elif measurements is not None:
        valid = api_status == 'passed' and verified and stage_matrix_valid(measurements, result)
        perf.update(status='measured' if valid else 'invalid_measurement',
                    credit=None if valid else 0, metrics=measurements)
    elif api_status == 'error':
        perf.update(status='error', credit=0)
    status = ('not_run' if result is None else 'failed' if api_status == 'failed'
              else 'error' if api_status == 'error' else 'partial'
              if coverage != 'full' or not verified else 'passed')
    record = {'schema_version': 1, 'run_id': run_id, 'release': release,
              'contract_sha256': contract_sha256, 'evaluator_sha256': evaluator_sha256,
              'provenance_status': 'verified' if verified else 'historical_incomplete',
              'missing_evidence': missing, 'environment': environment, 'coverage': coverage,
              'status': status, 'api': {'status': api_status, 'passed': passed, 'total': total},
              'performance': perf}
    for key in ('toksec_commit', 'toksec_dirty', 'run_toksec_commit'):
        if key in (result or {}):
            record[key] = result[key]
    validate_evaluation(record)
    json.dumps(record, allow_nan=False)
    files = ('evaluation.json', 'api.json', 'performance.json', 'report.md', 'figures')
    for name in files:
        if (output / name).is_symlink():
            raise ValueError('evaluation output must not follow symlinks')
    if (output / 'evaluation.json').exists():
        old = json.loads((output / 'evaluation.json').read_text())
        if old != record:
            raise ValueError('evaluation already exists; choose a new evaluation ID')
        return record
    output.mkdir(parents=True, exist_ok=True)
    (output / 'figures').mkdir(exist_ok=True)
    atomic_json(output / 'api.json', {'summary': record['api'], 'cases': cases,
                                     'build': (result or {}).get('build'),
                                     'unimplemented_requirements': checks.get('unimplemented_requirements',
                                         (result or {}).get('unimplemented_requirements', []))})
    atomic_json(output / 'performance.json', perf)
    text = [f'# Parent evaluation: {run_id}', '',
            f'Submission: `{release["tag"] or "unknown"}`. Commit: `{release["commit"] or "unknown"}`.',
            f'Coverage: **{coverage}**. Evaluation status: **{status}**.',
            f'API: {passed}/{total} behavioral checks passed.' if total is not None else 'API checks were not run.',
            f'Performance: **{perf["status"]}**.', '',
            'A skipped performance test has no measured throughput or latency.',
            'Zero performance credit is not a measured throughput of zero.', '',
            'See api.json and performance.json for evidence. Figures belong in figures/.']
    if record.get('toksec_commit'):
        text += ['', f"Toksec evaluator commit: `{record['toksec_commit']}`. Working tree dirty: {record.get('toksec_dirty', 'unknown')}."]
    if record.get('run_toksec_commit'):
        text += ['', f"Toksec run preparation commit: `{record['run_toksec_commit']}`."]
    if environment.get('mode') == 'comparison':
        text += ['', 'The parent regraded this release against its original stage specification.',
                 f"Builder framework `{environment['builder_framework']}`.",
                 f"Comparison evaluator `{environment['evaluator_framework']}`."]
        calibration = environment.get('calibration')
        if calibration:
            text.append(f"Calibration `{calibration['id']}` (SHA-256 `{calibration['sha256']}`).")
        elif measurements:
            text.append('No matching calibration was supplied for this comparison.')
    if missing:
        text += ['', 'Historical evidence is missing: ' + ', '.join(missing) + '.']
    if coverage != 'full':
        text += ['', 'This report does not establish full-stage acceptance.']
    if perf['status'] == 'provisional':
        text += ['', 'Performance values are uncalibrated diagnostics, not final scores. No performance credit is awarded.']
    failures = [c for c in cases if not c['passed']]
    if failures:
        text += ['', 'Failed checks:', '']
        text += [f'- `{c.get("id", "unknown")}`: {c.get("explanation", c.get("error", "failed"))}' for c in failures]
    (output / 'report.md').write_text('\n'.join(text) + '\n')
    atomic_json(output / 'evaluation.json', record)
    return record
