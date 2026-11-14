#!/usr/bin/env python3
"""Serial full evaluation of reference sources; does not launch model agents."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller import atomic_json
from toksec import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=int, choices=range(1, 6), action='append')
    parser.add_argument('--language', choices=('cpp', 'rust'), action='append')
    parser.add_argument('--section', choices=('api', 'performance'), default='api')
    parser.add_argument('--cpus', required=True, help='Explicit comma-separated available CPU IDs; minimum runs server, maximum runs upstream')
    parser.add_argument('--output', type=Path, help='New output directory')
    args = parser.parse_args()
    cpus = {int(value) for value in args.cpus.split(',')}
    if not cpus <= os.sched_getaffinity(0):
        parser.error('requested CPUs are not all available')
    stages = sorted(set(args.stage or range(1, 6)))
    languages = sorted(set(args.language or ('cpp', 'rust')))
    needed = (6 if max(stages) >= 4 else 5) if args.section == 'performance' else (2 if max(stages) >= 4 else 1)
    if len(cpus) < needed:
        parser.error(f'this evaluation needs at least {needed} CPUs')
    targets = []
    for stage in stages:
        for language in languages:
            source = ROOT / 'references' / f'stage-{stage:02}' / language / ('main.cpp' if language == 'cpp' else 'main.rs')
            if not source.is_file():
                parser.error(f'missing reference source: {source}')
            targets.append((stage, language, source))
    output = (args.output or ROOT / '.runs/references/validation' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')).resolve()
    lockpath = ROOT / '.runs/references/validation.lock'
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    with lockpath.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('another reference validation owns the lock; avoid competing benchmark runs')
        os.sched_setaffinity(0, cpus)
        output.mkdir(parents=True, exist_ok=False)
        summary = {'section': args.section, 'cpus': sorted(cpus), 'targets': []}
        failed = False
        for stage, language, source in targets:
            destination = output / f'stage-{stage:02}-{language}'
            entry = {'stage': stage, 'language': language, 'source': str(source), 'output': str(destination), 'status': 'running'}
            summary['targets'].append(entry)
            atomic_json(output / 'summary.json', summary)
            print(f'Evaluating stage {stage} {language}: {destination}', flush=True)
            try:
                result = evaluate.evaluate(source, destination, stage, args.section == 'performance', language=language)
                passed = result.get('checks', {}).get('passed', False)
                measures = result.get('benchmarks', {})
                valid = bool(measures) and all(v['eligible'] and v['failures'] == 0 for v in measures.values())
                entry.update(source_sha256=result['source_sha256'], framework=result['framework'],
                             api_passed=passed, grading=result['grading'],
                             performance_eligible=valid if args.section == 'performance' else None,
                             status='complete')
                failed |= not passed or (args.section == 'performance' and not valid)
            except Exception as error:
                entry.update(status='error', error=f'{type(error).__name__}: {error}')
                failed = True
            atomic_json(output / 'summary.json', summary)
        print(json.dumps(summary, indent=2))
        return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
