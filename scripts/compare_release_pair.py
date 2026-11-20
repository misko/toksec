#!/usr/bin/env python3
"""Confirm a preregistered workload on the first API-clean source and the final tag."""
import argparse
import hashlib
import json
import math
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec import benchmark, controller, releases, sandbox
from toksec.artifacts import validate_evaluation
from toksec.languages import source_name
from toksec.provenance import run_identity
from toksec.specification import workloads
from toksec.storage import atomic_json


def compare_tags(run, timeline, calibration, workload_id):
    manifest = controller.read(run, 'manifest.json')
    identity = run_identity(run, manifest)
    stage = timeline['stage']
    environment = releases.grade_environment(run, manifest, comparison=True, calibration=calibration)
    recorded = releases.list_releases(run)
    rows = timeline['releases']
    fields = ('tag', 'commit', 'source_sha256')
    if (timeline['run_id'] != identity or stage != manifest['stage']
            or timeline['framework'] != environment['evaluator_framework']
            or timeline.get('calibration') != environment['calibration']
            or [[r[k] for k in fields] for r in rows] != [[r[k] for k in fields] for r in recorded]):
        raise ValueError('timeline differs from the sealed release history, evaluator or calibration')
    selected = next((w for w in workloads(stage) if w.id == workload_id), None)
    if selected is None:
        raise ValueError('workload is absent from the stage contract')

    evaluations = []
    for row in rows:
        evaluation_id = row['evaluation_id']
        if uuid.UUID(evaluation_id).hex != evaluation_id:
            raise ValueError('invalid evaluation ID')
        envelope = validate_evaluation(controller.read(run / 'evaluation' / evaluation_id, 'evaluation.json'))
        if (envelope['run_id'] != identity or envelope['release'] != {k: row[k] for k in fields}
                or envelope['evaluator_sha256'] != environment['evaluator_framework']
                or envelope['contract_sha256'] != manifest['artifact_sha256']
                or envelope['environment'].get('calibration') != environment['calibration']):
            raise ValueError('timeline references an unrelated parent evaluation')
        evaluations.append(envelope)

    receipt = {'run_id': identity, 'workload': workload_id, 'calibration_id': environment['calibration']['id'],
               'evaluator_sha256': environment['evaluator_framework'], 'status': 'unavailable'}
    passed = [e for e in evaluations if e['coverage'] == 'full' and e['api']['status'] == 'passed']
    if not passed or passed[-1] != evaluations[-1]:
        return {**receipt, 'reason': 'final tag lacks a full independent API pass'}
    first, last = passed[0]['release'], passed[-1]['release']
    receipt.update(first_release=first, final_release=last)
    if first['source_sha256'] == last['source_sha256']:
        return {**receipt, 'reason': 'one distinct API-clean endpoint'}
    control = json.loads(calibration.read_text())['cells'][workload_id]
    if not control['qualified']:
        return {**receipt, 'reason': 'confirmation cell did not qualify', 'issues': control['reasons']}
    noise = control['aa_noise_fraction']
    if not isinstance(noise, (float, int)) or not math.isfinite(noise) or noise < 0:
        raise ValueError('missing finite calibration noise fraction')

    rounds = {'first': [], 'final': []}
    language = manifest['language']
    with tempfile.TemporaryDirectory(prefix='toksec-confirm-') as temporary:
        root = Path(temporary)
        for name, release in [('first', first), ('final', last)]:
            source = releases.git(run, 'show', release['commit'] + ':' + source_name(manifest))
            if hashlib.sha256(source.encode()).hexdigest() != release['source_sha256']:
                raise ValueError('tagged source no longer matches parent receipt')
            build = sandbox.build(source, root / name, stage, language=language)
            if not build['passed'] or not sandbox.evaluate(root / name, stage)['passed']:
                return {**receipt, 'reason': 'paired rebuild failed the API gate', 'endpoint': name}
        for index in range(selected.rounds):
            order = ('first', 'final') if index % 2 == 0 else ('final', 'first')
            for name in order:
                result = sandbox.invoke_driver(root / name, stage, 'benchmark', workload=workload_id, rounds=1)
                rounds[name].extend(result[workload_id]['rounds'])

    summaries = {k: benchmark.summarize(v, selected) for k, v in rounds.items()}
    receipt.update(summaries=summaries, aa_noise_fraction=noise)
    if not all(benchmark.cell_valid(v, selected) for v in summaries.values()):
        return {**receipt, 'reason': 'paired confirmation contains an invalid cell'}
    verdict = benchmark.compare({workload_id: summaries['first']}, {workload_id: summaries['final']}, [selected])
    gain = summaries['final']['median_rps'] / summaries['first']['median_rps'] - 1
    improved = verdict['promote'] and gain > noise
    return {**receipt, 'status': 'improved' if improved else 'gain_unconfirmed',
            'goodput_gain_fraction': gain, 'comparison': verdict}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--calibration', required=True, type=Path)
    parser.add_argument('--workload', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = compare_tags(args.run.resolve(), json.loads(args.timeline.read_text()), args.calibration, args.workload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'summaries'}, indent=2))
