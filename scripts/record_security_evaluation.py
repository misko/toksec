#!/usr/bin/env python3
"""Record a security analysis against a release; never execute evidence or call a model."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.security_evaluations import record_security_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--figures', type=Path)
    parser.add_argument('--evaluation-id')
    args = parser.parse_args()
    try:
        record = record_security_evaluation(args.run, tag=args.tag,
            analysis=json.loads(args.analysis.read_text()), report=args.report,
            evidence=args.evidence, figures=args.figures, evaluation_id=args.evaluation_id)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
