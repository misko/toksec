#!/usr/bin/env python3
"""Publish only latest no-starter, smoke-only runs; never modify source campaigns."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read(path):
    return json.loads(path.read_text())


def select(roots):
    latest = {}
    for root in roots:
        for path in sorted((root/'.runs').glob('**/manifest.json')):
            manifest = read(path)
            level = manifest.get('stage', manifest.get('level'))
            if (level not in (1,2,3,4,5,10)
                or not manifest.get('started_unix')
                or manifest.get('builder_evaluation_scope') != 'visible_smoke_only'
                or manifest.get('starter_candidate') or manifest.get('starter_sha256')):
                continue
            language = manifest.get('language', 'rust')
            if language not in ('rust', 'cpp'):
                continue
            key = (level, language)
            if key not in latest or manifest['started_unix'] > latest[key][1]['started_unix']:
                latest[key] = (path.parent, manifest)
    return latest


def publish(roots, output):
    from toksec.result_storage import publish_run, update_index
    output.mkdir(parents=True, exist_ok=True)
    for run, manifest in select(roots).values():
        publish_run(run, output)
    return update_index(output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,action='append',required=True,help='Frozen repository worktree containing .runs')
    parser.add_argument('--output',type=Path,default=Path('results'))
    args=parser.parse_args()
    print(json.dumps(publish([p.resolve() for p in args.source],args.output.resolve()),indent=2))
