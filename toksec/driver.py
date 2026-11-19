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
from toksec.checks import Context, run_checks, cases_for, configured_cases
from toksec.specification import workloads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', '--level', dest='stage', type=int, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--private', type=Path)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--server-cpu', type=int, required=True)
    parser.add_argument('--mode', choices=('check', 'benchmark'), required=True)
    parser.add_argument('--suite', choices=('full', 'smoke'), default='full')
    parser.add_argument('--case')
    parser.add_argument('--workload')
    parser.add_argument('--rounds', type=int, default=5)
    args = parser.parse_args()
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, max(soft, 16384)), hard))
    upstream = None
    upstream_cpu = None
    try:
        if args.stage >= 4:
            ready = args.fixtures / 'upstream.ready'
            fixture_module = 'stages.common.smoke.upstream' if args.suite == 'smoke' or args.mode == 'benchmark' else 'toksec.fixtures'
            available = sorted(os.sched_getaffinity(0) - {args.server_cpu})
            if args.mode == 'benchmark' and len(available) < 5:
                raise RuntimeError('proxy benchmarks need one server, four generator and one upstream CPU')
            upstream_cpu = available[-1]
            fixture_args = [fixture_module, str(ready)]
            if args.stage in range(11, 17):
                fixture_args = ['stages.common.grading.gateway_origin', str(args.stage), str(args.fixtures), str(args.private)]
            upstream = subprocess.Popen(['taskset', '-c', str(upstream_cpu), sys.executable, '-m', *fixture_args],
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
            selected = None
            if args.suite == 'smoke':
                from stages.common.smoke.api import cases
                selected = cases(args.stage)
                if args.case:
                    raise ValueError('smoke suite cannot select a held-out case')
            if args.case:
                selected = [c for c in cases_for(args.stage) + configured_cases(args.stage) if c.id == args.case]
                if len(selected) != 1:
                    raise ValueError('unknown or ambiguous case')
            result = run_checks(Context(args.stage, args.fixtures, args.pid, args.private), selected)
        else:
            selected = [w for w in workloads(args.stage) if not args.workload or w.id == args.workload]
            if not selected or not 1 <= args.rounds <= 5:
                raise ValueError('invalid workload or rounds')
            result = {}
            for workload in selected:
                rounds = []
                for _ in range(args.rounds):
                    gateway = args.stage in range(11, 17)
                    if gateway:
                        from stages.common.grading.gateway_load import control, validate_effects
                        before = control(args.private)
                    measurement = round_run(workload, args.pid, args.server_cpu, args.fixtures,
                                            upstream_pid=upstream.pid if upstream else None,
                                            upstream_cpu=upstream_cpu)
                    if gateway:
                        validate_effects(args.stage, measurement, before, control(args.private))
                    rounds.append(measurement)
                result[workload.id] = summarize(rounds)
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
