#!/usr/bin/env python3
"""Evaluate HTTP source or the latest tagged release with the public suite."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from toksec import evaluate, releases, campaign, controller


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section', required=True, choices=('api','performance'))
    parser.add_argument('--source', type=Path, default=Path('main.rs'))
    parser.add_argument('--level', type=int, choices=range(1,6))
    parser.add_argument('--run', type=Path, help='Grade the latest completed Git release of this run instead of a source file')
    parser.add_argument('--output', type=Path, help='New directory for sources, diagnostics and JSON results')
    args=parser.parse_args(argv)
    output=args.output or Path('evaluation-results')/uuid.uuid4().hex
    try:
        if args.run:
            with campaign.locked(controller.read(args.run,'manifest.json')['campaign'],owner=True):
                result=releases.grade(args.run,output,args.section=='performance')
        else:
            level=args.level
            if level is None:
                level=json.loads(Path('evaluation.json').read_text())['level']
            result=evaluate.evaluate(args.source,output,level,args.section=='performance')
        result['section']=args.section
        result['output']=str(output.resolve())
        from controller import atomic_json
        atomic_json(output/'result.json',result)
        print(json.dumps(result,indent=2,allow_nan=False))
        if not result.get('checks',{}).get('passed'):
            return 2
        if args.section=='performance' and (not result.get('benchmarks') or not all(v['eligible'] and v['failures']==0 for v in result['benchmarks'].values())):
            return 3
        return 0
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        print(json.dumps({'error':str(error),'section':args.section}),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
