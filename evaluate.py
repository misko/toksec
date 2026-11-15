#!/usr/bin/env python3
"""Evaluate HTTP source or the latest tagged release with the independent parent API suite."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from toksec import evaluate, releases
from toksec.stage_dispatch import operation_lock


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section', required=True, choices=('api','performance'))
    parser.add_argument('--source', type=Path, default=None)
    parser.add_argument('--language', choices=('rust', 'cpp'), default='rust')
    parser.add_argument('--level', type=int, choices=(1,2,3,4,5,10))
    parser.add_argument('--run', type=Path, help='Grade the latest completed Git release of this run instead of a source file')
    parser.add_argument('--output', type=Path, help='New directory for sources, diagnostics and JSON results')
    args=parser.parse_args(argv)
    output=args.output or ((args.run/'evaluation' if args.run else Path('evaluation-results'))/uuid.uuid4().hex)
    try:
        if args.run:
            with operation_lock(args.run):
                result=releases.grade(args.run,output,args.section=='performance')
        else:
            level=args.level
            if level is None:
                level=json.loads(Path('evaluation.json').read_text())['level']
            source=args.source or Path('main.cpp' if args.language == 'cpp' else 'main.rs')
            result=evaluate.evaluate(source,output,level,args.section=='performance',language=args.language)
        result['section']=args.section
        result['output']=str(output.resolve())
        from toksec.storage import atomic_json
        atomic_json(output/'result.json',result)
        print(json.dumps(result,indent=2,allow_nan=False))
        return evaluate.exit_code(result,args.section=='performance')
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        print(json.dumps({'error':str(error),'section':args.section}),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
