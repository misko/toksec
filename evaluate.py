#!/usr/bin/env python3
"""Evaluate HTTP source or the latest tagged release with the independent parent API suite."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from toksec import evaluate, releases
from toksec.stages import SUPPORTED_STAGES, number as stage_number
from toksec.stage_dispatch import operation_lock


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section', required=True, choices=('api','performance'))
    parser.add_argument('--source', type=Path, default=None)
    parser.add_argument('--language', choices=('rust', 'cpp'), default='rust')
    parser.add_argument('--stage', '--level', dest='stage', type=int, choices=SUPPORTED_STAGES)
    parser.add_argument('--run', type=Path, help='Grade the latest completed Git release of this run instead of a source file')
    parser.add_argument('--tag', help='Grade this exact completed release/NNNNNN (defaults to the last tag)')
    parser.add_argument('--comparison', action='store_true', help='Remeasure a finished run with the current evaluator and verify its frozen stage specification')
    parser.add_argument('--calibration', type=Path, help='Gateway calibration.json for the current grading environment')
    parser.add_argument('--output', type=Path, help='New directory for sources, diagnostics and JSON results')
    args=parser.parse_args(argv)
    if (args.tag or args.comparison or args.calibration) and not args.run:
        parser.error('--tag, --comparison and --calibration require --run')
    output=args.output or ((args.run/'evaluation' if args.run else Path('evaluation-results'))/uuid.uuid4().hex)
    try:
        if args.run:
            with operation_lock(args.run):
                options = {}
                if args.tag is not None:
                    options['tag'] = args.tag
                if args.comparison:
                    options['comparison'] = True
                if args.calibration is not None:
                    options['calibration'] = args.calibration
                result = releases.grade(args.run, output, args.section == 'performance', **options)
        else:
            level=args.stage
            if level is None:
                level=stage_number(json.loads(Path('evaluation.json').read_text()))
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
