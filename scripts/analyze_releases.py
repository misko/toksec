#!/usr/bin/env python3
"""Independently grade each numbered release and write a time and spend timeline."""
import argparse
import hashlib
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec import controller, releases
from toksec.artifacts import validate_evaluation
from toksec.languages import source_name
from toksec.provenance import run_identity
from toksec.specification import specification
from toksec.stage_dispatch import operation_lock
from toksec.stages import number as stage_number
from toksec.storage import atomic_json


def export_history(run, output, tip):
    bundle = output / 'implementation.bundle'
    repository = output / 'implementation'
    if not bundle.exists():
        subprocess.run(['git', '-C', str(run / 'repository'), '-c', 'core.hooksPath=/dev/null',
                        'bundle', 'create', str(bundle), '--tags'], check=True, capture_output=True)
    if not repository.exists():
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-checkout',
                        str(bundle), str(repository)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(repository), '-c', 'core.hooksPath=/dev/null', 'checkout',
                    '--detach', tip['commit']], check=True, capture_output=True)
    return repository


def analyze(run, output, *, comparison=False, calibration=None, performance=True):
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.is_relative_to(run / 'repository') or output.is_relative_to(run / 'evaluation'):
        raise ValueError('place the analysis workspace outside the submitted repository and evaluation envelopes')
    with operation_lock(run):
        return _analyze(run, output, comparison, calibration, performance)


def _analyze(run, output, comparison, calibration, performance):
    manifest = controller.read(run, 'manifest.json')
    state = controller.read(run)
    if not state['finished']:
        raise ValueError('Wait until the builder has finished before benchmarking releases')
    stage = stage_number(manifest)
    if stage == 10:
        raise ValueError('Stage 10 uses the separate partial-coverage grader in evaluate.py')
    environment = releases.grade_environment(run, manifest, comparison=comparison, calibration=calibration)
    records = releases.list_releases(run)
    if not records:
        raise ValueError('Builder produced no tagged releases')
    identity = run_identity(run, manifest)
    request = {'run_id': identity, 'run_toksec_commit': manifest.get('toksec_commit'),
               'tagged_commits': {r['tag']: r['commit'] for r in records},
               'environment': environment, 'performance_requested': performance}
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / 'series.json'
    if plan_path.exists():
        plan = controller.read(output, 'series.json')
        if plan['request'] != request:
            raise ValueError('analysis workspace belongs to another source, evaluator, host or measurement policy; choose a new output directory')
    else:
        if any(output.iterdir()):
            raise ValueError('analysis workspace has earlier evidence; choose a new empty output directory')
        plan = {'request': request, 'evaluations': {r['tag']: uuid.uuid4().hex for r in records}}
        atomic_json(plan_path, plan)
    if (run / 'benchmarks').exists() and not (output / 'in-run-benchmarks').exists():
        shutil.copytree(run / 'benchmarks', output / 'in-run-benchmarks')
    repository = export_history(run, output, records[-1])
    final = controller.read(run, 'result.json') if (run / 'result.json').is_file() else {}
    timeline = {'run_id': identity, 'stage': stage, 'framework': environment['evaluator_framework'],
                'builder_framework': manifest['fingerprint'], 'run_toksec_commit': manifest.get('toksec_commit'),
                'per_tag_evaluations': True, 'language': manifest.get('language', 'rust'),
                'started_unix': manifest['started_unix'], 'ended_unix': state.get('ended_unix'),
                'terminal_capacity': final.get('capacity'), 'stop_reason': state.get('stop_reason'),
                'workloads': environment['workloads'], 'calibration': environment['calibration'],
                'total_checks': len(specification(stage, manifest.get('language', 'rust'))['cases']),
                'method': 'Independent post-run grades at release publication time and recorded cumulative settled cost.',
                'releases': []}
    for record in records:
        tag = record['tag']
        source_file = source_name(manifest)
        source = subprocess.check_output(['git', '-C', str(repository), 'show', tag + ':' + source_file])
        commit = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', tag + '^{commit}'], text=True).strip()
        if commit != record['commit'] or hashlib.sha256(source).hexdigest() != record['source_sha256']:
            raise ValueError('exported release differs from recorded Git identity')
        stem = tag.replace('/', '-')
        (output / (stem + Path(source_file).suffix)).write_bytes(source)
        evaluation_id = plan['evaluations'][tag]
        destination = run / 'evaluation' / evaluation_id
        if destination.is_symlink() or uuid.UUID(evaluation_id).hex != evaluation_id:
            raise ValueError('invalid series evaluation ID')
        if not (destination / 'evaluation.json').exists():
            print(f'Grading {identity} {tag}', flush=True)
            if destination.exists() and not (destination / 'result.json').exists():
                # No completed API receipt. Keep interrupted diagnostics outside the
                # envelope collection, then rebuild this immutable source.
                shutil.move(str(destination), str(output / f'{stem}-interrupted-{time.time_ns()}'))
            releases.grade(run, destination, performance, tag=tag, comparison=comparison,
                           calibration=calibration, resume=True)
        envelope = validate_evaluation(controller.read(destination, 'evaluation.json'))
        release = {key: record[key] for key in ('tag', 'commit', 'source_sha256')}
        if (envelope['run_id'] != identity or envelope['release'] != release
                or envelope['environment'] != environment
                or envelope['contract_sha256'] != manifest.get('artifact_sha256')
                or envelope['evaluator_sha256'] != environment['evaluator_framework']):
            raise ValueError('cached parent evaluation does not match this release or measurement environment')
        api = controller.read(destination, 'api.json')
        perf = envelope['performance']
        timeline['releases'].append({**record, 'evaluation_id': evaluation_id,
            'elapsed_seconds': max(0, record['recorded_unix'] - manifest['started_unix']),
            'spent_usd_upper_bound': record.get('capacity', {}).get('spent_usd_upper_bound'),
            'api_status': envelope['api']['status'], 'passed': envelope['api']['passed'],
            'cases': api['cases'], 'build_passed': bool((api.get('build') or {}).get('passed')),
            'performance_status': perf['status'], 'benchmarks': perf['metrics'] or {},
            'evaluated_unix': (destination / 'evaluation.json').stat().st_mtime})
        atomic_json(output / 'timeline.json', timeline)
    return timeline


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New or resumable analysis workspace')
    parser.add_argument('--comparison', action='store_true', help='Verify the frozen contract and explicitly use the current evaluator')
    parser.add_argument('--calibration', type=Path, help='Gateway calibration.json from the same host and workload configuration')
    parser.add_argument('--api-only', action='store_true', help='Independently regrade all API checks without load generation')
    args = parser.parse_args()
    analyze(args.run, args.output, comparison=args.comparison, calibration=args.calibration,
            performance=not args.api_only)
