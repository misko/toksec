"""Host-owned Stage 10 smoke and preliminary API orchestration."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from toksec.storage import atomic_json
from toksec.sandbox import cgroup as sandbox

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'stages/stage-10/fixtures'


def fixtures(destination, bootstrap=False):
    destination = Path(destination)
    shutil.copytree(FIXTURES, destination)
    if bootstrap:
        shutil.copyfile(destination / 'config/bootstrap.conf', destination / 'config/nginx.conf')
    return destination


def evaluate(artifact, output, mode='smoke', cpus=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cpus = list(cpus or sorted(os.sched_getaffinity(0))[:1])
    cases = []
    reports = []
    for bootstrap in (True, False):
        name = 'bootstrap' if bootstrap else mode
        directory = fixtures(output / (name + '-fixtures'), bootstrap)
        result_path = output / (name + '.json')
        if not bootstrap:
            try:
                with sandbox.running(artifact, directory, cpus=cpus, workers=2, timeout=20,
                                     args=['--check-config', '/fixtures/config/nginx.conf'],
                                     wait_for_pid=False) as runtime:
                    try:
                        code = runtime['process'].wait(timeout=25)
                    finally:
                        shutil.copyfile(runtime['log'], output / 'config-server.log')
                cases.append({'id': 'config', 'passed': code == 0,
                              'explanation': f'--check-config exit status {code}'})
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                cases.append({'id': 'config', 'passed': False, 'explanation': str(error)[:2000]})
        try:
            with sandbox.running(artifact, directory, cpus=cpus, workers=1 if bootstrap else 2,
                                 timeout=180) as runtime:
                try:
                    command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net',
                               '--preserve-credentials', '--', '/usr/bin/python3', '-m', 'stages.stage-10.grading.checks',
                               '--mode', mode, '--fixtures', str(directory), '--output', str(result_path)]
                    if bootstrap:
                        command.append('--bootstrap')
                    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=150)
                    (output / (name + '-driver.log')).write_text(done.stdout + done.stderr)
                    if not result_path.exists():
                        raise RuntimeError('checker did not produce a result: ' + done.stderr[-2000:])
                    report = json.loads(result_path.read_text())
                    reported_cases = report.get('cases')
                    if not isinstance(reported_cases, list) or not reported_cases:
                        raise RuntimeError('checker returned no cases: ' + str(report.get('error', ''))[:1500])
                    if not all(isinstance(case, dict) and isinstance(case.get('id'), str)
                               and isinstance(case.get('passed'), bool) for case in reported_cases):
                        raise RuntimeError('checker returned malformed cases')
                    cases.extend(reported_cases)
                    reports.append(report)
                    if done.returncode != 0 or report.get('passed') is not True:
                        raise RuntimeError('checker reported failure or exited nonzero')
                finally:
                    shutil.copyfile(runtime['log'], output / (name + '-server.log'))
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            cases.append({'id': name + '-runtime', 'passed': False, 'explanation': str(error)[:2000]})
    result = {'passed': bool(cases) and all(c['passed'] for c in cases), 'cases': cases,
              'scope': 'visible_smoke' if mode == 'smoke' else 'preliminary_independent_api',
              'final_grade_eligible': False,
              'unimplemented_requirements': sorted(set(
                  ['complete configuration matrix', 'worker/reload/global-resource behavior',
                   'complete Stage 10 API gate and calibrated performance matrix'] +
                  [item for r in reports for item in r.get('unimplemented_requirements', [])]))}
    atomic_json(output / 'result.json', result)
    return result
