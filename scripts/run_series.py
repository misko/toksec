#!/usr/bin/env python3
"""Run independently budgeted experiments sequentially, then grade and plot tags."""
import argparse
import os
import threading
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toksec.storage import atomic_json
from toksec import campaign, controller, releases, reporting, runner


def analyze(run, plot_python):
    for attempt in range(2):
        output = run / 'analysis'
        result = subprocess.run([sys.executable, str(ROOT/'scripts/analyze_releases.py'), '--run', str(run), '--output', str(output)], cwd=ROOT)
        if result.returncode == 0:
            subprocess.run([str(plot_python), str(ROOT/'scripts/plot_releases.py'), str(output)], check=True, cwd=ROOT)
            return output
        print(json.dumps({'event': 'analysis_failed', 'run': str(run), 'attempt': attempt+1}), flush=True)
    raise RuntimeError('Independent analysis failed twice; partial results retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grade-only', action='store_true', help='Resume grading finished runs; never call model API')
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--plot-python', type=Path, required=True)
    parser.add_argument('--status-file', type=Path, required=True)
    args = parser.parse_args()
    if not args.grade_only and not args.key_file:
        parser.error('--key-file required unless --grade-only')
    def heartbeat():
        while True:
            atomic_json(args.status_file.with_suffix('.heartbeat.json'), {'pid': os.getpid(), 'updated_unix': time.time()})
            time.sleep(10)
    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    runs = [r.resolve() for r in args.run]
    status = {'runs': [{'run': str(r), 'status': 'queued'} for r in runs]}
    atomic_json(args.status_file, status)
    for index, run in enumerate(runs):
        entry = status['runs'][index]
        entry.update(status='building', started_unix=time.time())
        atomic_json(args.status_file, status)
        try:
            if args.grade_only:
                if not controller.read(run)['finished']:
                    raise ValueError('grade-only requires a finished builder; it never resumes model calls')
            else:
                check = runner.preflight(run)
                if not check['launch_allowed']:
                    raise ValueError('; '.join(check['reasons']))
                print(json.dumps({'event': 'builder_started', 'run': str(run)}), flush=True)
                runner.run_loop(run, runner.Responses(runner.credentials(args.key_file)))
            (run/'progress.md').write_text(reporting.markdown(run))
            manifest = controller.read(run, 'manifest.json')
            records = releases.list_releases(run)
            entry.update(status='grading', tagged_releases=len(records), capacity=campaign.status(manifest['campaign'],manifest['model']))
            atomic_json(args.status_file, status)
            print(json.dumps({'event': 'builder_finished', **entry}), flush=True)
            if records:
                output = analyze(run, args.plot_python)
                entry['analysis'] = str(output)
            entry.update(status='complete', completed_unix=time.time())
            atomic_json(run/'completion.json',entry)
        except Exception as error:
            entry.update(status='error', error_type=type(error).__name__, error=str(error)[:2000])
            atomic_json(run/'worker-error.json',entry)
            print(json.dumps(entry),flush=True)
        atomic_json(args.status_file,status)
    print(json.dumps({'event': 'series_complete', **status}), flush=True)


if __name__ == '__main__':
    main()
