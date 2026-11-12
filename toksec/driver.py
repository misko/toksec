import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import os
import resource
import socket
import subprocess
import time

from toksec.benchmark import round_run, summarize
from toksec.checks import Context, run_checks
from toksec.specification import workloads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--level', type=int, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--server-cpu', type=int, required=True)
    parser.add_argument('--mode', choices=('check', 'benchmark'), required=True)
    parser.add_argument('--workload')
    parser.add_argument('--rounds', type=int, default=5)
    args = parser.parse_args()
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, max(soft, 16384)), hard))
    upstream = None
    try:
        if args.level >= 4:
            ready = args.fixtures / 'upstream.ready'
            upstream = subprocess.Popen([sys.executable, '-m', 'toksec.fixtures', str(ready)],
                                        cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            end = time.monotonic() + 2
            while not ready.exists():
                if time.monotonic() > end:
                    raise TimeoutError('upstream fixture did not start')
                time.sleep(0.01)
        end = time.monotonic() + 2
        while True:
            try:
                with socket.create_connection(('127.0.0.1', 8080), 0.1):
                    break
            except OSError:
                if time.monotonic() > end:
                    raise TimeoutError('server did not bind within two seconds')
                time.sleep(0.01)
        if args.mode == 'check':
            result = run_checks(Context(args.level, args.fixtures, args.pid))
        else:
            selected = [w for w in workloads(args.level) if not args.workload or w.id == args.workload]
            if not selected or not 1 <= args.rounds <= 5:
                raise ValueError('invalid workload or rounds')
            result = {w.id: summarize([round_run(w, args.pid, args.server_cpu, args.fixtures) for _ in range(args.rounds)]) for w in selected}
        print(json.dumps(result, allow_nan=False))
    finally:
        if upstream:
            upstream.terminate()
            try:
                upstream.wait(timeout=3)
            except subprocess.TimeoutExpired:
                upstream.kill()
                upstream.wait()


if __name__ == '__main__':
    main()
