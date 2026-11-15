#!/usr/bin/env python3
"""Publish one completed or live raw run without exposing API conversations."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.result_storage import publish_run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--results', type=Path, default=Path('results'))
    args = parser.parse_args()
    print(json.dumps(publish_run(args.run, args.results), indent=2))
