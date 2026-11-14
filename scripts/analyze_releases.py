#!/usr/bin/env python3
"""Export a completed builder Git history and independently evaluate every tag."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import atomic_json
from toksec import controller, evaluate, releases
from toksec.languages import source_name
from toksec.specification import fingerprint, specification


def analyze(run, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    manifest = controller.read(run, 'manifest.json')
    state = controller.read(run)
    if not state['finished']:
        raise ValueError('Wait until the builder has finished before benchmarking releases')
    if manifest['fingerprint'] != fingerprint():
        raise ValueError('Use the original frozen evaluator checkout')
    records = releases.list_releases(run)
    if not records:
        raise ValueError('Builder produced no tagged releases')
    output.mkdir(parents=True, exist_ok=True)
    if (run / 'benchmarks').exists():
        shutil.copytree(run / 'benchmarks', output / 'in-run-benchmarks', dirs_exist_ok=True)
    bundle = output / 'implementation.bundle'
    if not bundle.exists():
        releases.git(run, 'bundle', 'create', '/workspace/releases.bundle', '--tags')
        shutil.copyfile(run / 'repository' / 'releases.bundle', bundle)
    repository = output / 'implementation'
    if not repository.exists():
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-checkout', str(bundle), str(repository)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(repository), '-c', 'core.hooksPath=/dev/null', 'checkout', '--detach', records[-1]['tag']], check=True, capture_output=True)
    timeline = {'level': manifest['level'], 'framework': manifest['fingerprint'], 'language': manifest.get('language', 'rust'),
                'started_unix': manifest['started_unix'], 'ended_unix': state.get('ended_unix'),
                'total_checks': len(specification(manifest['level'])['cases']),
                'method': 'Independent post-run measurements plotted at release publication time; no model API calls.',
                'releases': []}
    for record in records:
        tag = record['tag']
        print('Evaluating ' + tag, flush=True)
        source = subprocess.check_output(['git', '-C', str(repository), 'show', tag + ':' + source_name(manifest)])
        if hashlib.sha256(source).hexdigest() != record['source_sha256']:
            raise ValueError('Exported source does not match recorded hash')
        stem = tag.replace('/', '-')
        source_path = output / (stem + Path(source_name(manifest)).suffix)
        source_path.write_bytes(source)
        destination = output / stem
        result_path = destination / 'result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text())
            if not result.get('analysis_complete'):
                raise ValueError('Incomplete prior evaluation at ' + str(destination) + '; preserve it and use a fresh output directory')
        else:
            result = evaluate.evaluate(source_path, destination, manifest['level'], performance=True, language=manifest.get('language', 'rust'))
            result['analysis_complete'] = True
            result['evaluated_unix'] = time.time()
            atomic_json(result_path, result)
        cases = result.get('checks', {}).get('cases', [])
        timeline['releases'].append({**record,
            'elapsed_seconds': max(0, record['recorded_unix'] - manifest['started_unix']),
            'passed': sum(c['passed'] for c in cases), 'cases': cases,
            'build_passed': result['build']['passed'], 'benchmarks': result.get('benchmarks', {}),
            'evaluated_unix': result.get('evaluated_unix')})
        atomic_json(output / 'timeline.json', timeline)
        print(f"{tag}: {timeline['releases'][-1]['passed']}/{timeline['total_checks']} API checks", flush=True)
    return timeline


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    analyze(args.run, args.output)
