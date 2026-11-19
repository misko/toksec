#!/usr/bin/env python3
"""Validate historical migrations; add --run-ids to relocate publications and --apply to execute."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.result_storage import migrate
from toksec.result_migration import migrate_run_ids

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('results'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--run-ids', action='store_true', help='Move normalized historical snapshots to results/<recorded-raw-run-id>')
    args = parser.parse_args()
    selected = migrate_run_ids if args.run_ids else migrate
    print(json.dumps(selected(args.results, apply=args.apply), indent=2))
