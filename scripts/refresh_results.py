#!/usr/bin/env python3
"""Publish eligible runs and select latest entries without modifying raw campaigns."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.stages import number as stage_number


def read(path):
    return json.loads(path.read_text())


def eligible(roots):
    for root in roots:
        for path in sorted((root/'.runs').glob('**/manifest.json')):
            manifest = read(path)
            level = stage_number(manifest)
            if (level not in range(1,11)
                or not manifest.get('started_unix')
                or manifest.get('builder_evaluation_scope') != 'visible_smoke_only'
                or manifest.get('starter') or manifest.get('starter_candidate') or manifest.get('starter_sha256')):
                continue
            language = manifest.get('language', 'rust')
            if language not in ('rust', 'cpp'):
                continue
            yield path.parent, manifest


def select(roots):
    latest = {}
    for run, manifest in eligible(roots):
        key = (stage_number(manifest), manifest.get('language', 'rust'))
        order = lambda item: (item[1]['started_unix'], item[1].get('run_id', item[0].name))
        if key not in latest or order((run, manifest)) > order(latest[key]):
            latest[key] = (run, manifest)
    return latest


def publish(roots, output):
    from toksec.result_storage import publish_run, update_index
    output.mkdir(parents=True, exist_ok=True)
    for run, manifest in eligible(roots):
        publish_run(run, output)
    return update_index(output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,action='append',required=True,help='Frozen repository worktree containing .runs')
    parser.add_argument('--output',type=Path,default=Path('results'))
    args=parser.parse_args()
    print(json.dumps(publish([p.resolve() for p in args.source],args.output.resolve()),indent=2))
