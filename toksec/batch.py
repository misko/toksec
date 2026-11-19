"""Independent campaign caps and process-isolated parallel builder scheduling."""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from toksec.provenance import checkout
from toksec.specification import ROOT
from toksec.storage import atomic_json


def read(path):
    return json.loads(Path(path).read_text())


def command(cpus, *args):
    return ['taskset', '-c', ','.join(map(str, cpus)), sys.executable, '-m', 'toksec', *map(str, args)]


def capture(cpus, *args):
    done = subprocess.run(command(cpus, *args), cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        raise ValueError(done.stdout[-3000:] + done.stderr[-1000:])
    return json.loads(done.stdout)


def plan(stages, replicas, parallel, budget_usd, wall_seconds, language, cpus, budgets_usd=None):
    amounts = [Decimal(str(value)) for value in (budgets_usd if budgets_usd is not None else [budget_usd])]
    if not amounts or any(not value.is_finite() or not 0 < value <= 5 for value in amounts):
        raise ValueError('batch per-run budgets must be positive and at most $5')
    if len(set(amounts)) != len(amounts):
        raise ValueError('budget sweep values must be distinct')
    if not stages or len(set(stages)) != len(stages) or any(s not in (1, 5, 10) for s in stages):
        raise ValueError('choose distinct stages from 1, 5, and 10')
    if type(replicas) is not int or replicas < 1 or type(parallel) is not int or parallel < 1:
        raise ValueError('replicas and parallel must be positive integers')
    if not 120 <= wall_seconds <= 7200 or language not in ('cpp', 'rust'):
        raise ValueError('invalid wall limit or language')
    slots = min(parallel, replicas * len(stages) * len(amounts))
    if len(cpus) < slots * 6:
        raise ValueError(f'{slots * 6} distinct CPUs required for {slots} parallel slots')
    jobs = []
    for amount in amounts:
        for replica in range(1, replicas + 1):
            for stage in stages:
                slot = len(jobs) % slots
                suffix = f'-usd-{format(amount.normalize(), "f")}' if budgets_usd is not None else ''
                jobs.append({'id': f'stage-{stage:02d}-{language}-replica-{replica:02d}{suffix}',
                             'stage': stage, 'replica': replica, 'slot': slot,
                             'cpus': cpus[slot * 6:(slot + 1) * 6], 'budget_usd': str(amount),
                             'status': 'planned'})
    return {'schema_version': 1, 'model': 'gpt-6.1-terra', 'reasoning_effort': 'medium',
            'service_tier': 'default', 'language': language, 'parallel': slots,
            'wall_seconds': wall_seconds, 'total_cap_usd': str(sum((Decimal(j['budget_usd']) for j in jobs), Decimal(0))),
            'status': 'preparing', 'jobs': jobs}


def prepare(directory, **options):
    cpus = sorted(os.sched_getaffinity(0))
    batch = plan(cpus=cpus, **options)
    batch.update(checkout(require_clean=True))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / 'batch.json'
    atomic_json(path, batch)
    try:
        for job in batch['jobs']:
            campaign = directory / job['id']
            profile = 'legacy' if job['stage'] == 10 else 'bounded-32k'
            capture(job['cpus'], 'init', '--campaign', campaign, '--budget-usd', job['budget_usd'],
                    '--request-profile', profile)
            allocation = ['--spend-target-usd', job['budget_usd']] if job['stage'] == 10 else []
            result = capture(job['cpus'], 'prepare', '--campaign', campaign,
                             '--stage', job['stage'], '--language', batch['language'],
                             '--model', batch['model'], '--wall-seconds', batch['wall_seconds'], *allocation)
            job.update(run=result['run'], campaign=str(campaign), status='prepared')
            preflight = capture(job['cpus'], 'preflight', '--run', job['run'])
            if not preflight['launch_allowed']:
                raise ValueError(str(preflight['reasons']))
            atomic_json(path, batch)
        batch['status'] = 'prepared'
    except Exception as error:
        batch.update(status='preparation_failed', error=str(error))
        raise
    finally:
        atomic_json(path, batch)
    return batch


@contextmanager
def lock(directory):
    with (Path(directory) / 'batch.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def schedule(jobs, parallel, start, save, poll_seconds=1):
    active = {}
    try:
        while active or any(j['status'] == 'prepared' for j in jobs):
            busy = {job['slot'] for _, job in active.values()}
            for job in jobs:
                if len(active) >= parallel:
                    break
                if job['status'] == 'prepared' and job['slot'] not in busy:
                    job.update(status='starting', started_unix=time.time())
                    save()
                    process = start(job)
                    job.update(status='running', pid=process.pid)
                    active[process.pid] = (process, job)
                    busy.add(job['slot'])
                    save()
            for pid, (process, job) in list(active.items()):
                code = process.poll()
                if code is not None:
                    job.update(status='builder_stopped', returncode=code, ended_unix=time.time())
                    del active[pid]
                    save()
            if active:
                time.sleep(poll_seconds)
    except BaseException:
        for process, job in active.values():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            job['status'] = 'interrupted'
        save()
        raise


def finalize(directory, batch, results):
    path = Path(directory) / 'batch.json'
    batch['status'] = 'finalizing'
    atomic_json(path, batch)
    for job in batch['jobs']:
        if job.get('status') in ('complete', 'no_tag'):
            continue
        run = Path(job['run'])
        try:
            records = capture(job['cpus'], 'releases', '--run', run)['releases']
            job['tag_count'] = len(records)
            if records:
                with (run / 'parent-grading.log').open('w') as log:
                    done = subprocess.run(command(job['cpus'], 'grade', '--run', run, '--performance'),
                                          cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                job['grade_exit_code'] = done.returncode
                if done.returncode not in (0, 2, 3, 4):
                    raise ValueError('parent grading failed; inspect parent-grading.log')
            with (run / 'publication.log').open('w') as log:
                done = subprocess.run([sys.executable, str(ROOT / 'scripts/publish_results.py'),
                                       '--run', str(run), '--results', str(results)],
                                      cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if done.returncode:
                raise ValueError('publication failed; inspect publication.log')
            job.update(status='complete' if records else 'no_tag', published=str(Path(results) / run.name))
        except Exception as error:
            job.update(status='finalization_failed', error=str(error))
        atomic_json(path, batch)
    batch['status'] = 'complete' if all(j['status'] == 'complete' for j in batch['jobs']) else 'completed_with_failures'
    atomic_json(path, batch)
    return batch


def launch(directory, key_file, results):
    from toksec.runner import credentials
    directory = Path(directory).resolve()
    with lock(directory):
        batch = read(directory / 'batch.json')
        if batch['status'] != 'prepared' or any(j['status'] != 'prepared' for j in batch['jobs']):
            raise ValueError('batch already started or not prepared; automatic paid resume is disabled')
        if checkout(require_clean=True)['toksec_commit'] != batch['toksec_commit']:
            raise ValueError('use the original batch preparation commit')
        credentials(key_file)
        authorized = sum((Decimal(j['budget_usd']) for j in batch['jobs']), Decimal(0))
        if authorized != Decimal(batch['total_cap_usd']):
            raise ValueError('batch budget does not match its independent allocations')
        for job in batch['jobs']:
            ledger = read(Path(job['campaign']) / 'ledger.json')
            if Decimal(ledger['dollar_limit']) != Decimal(job['budget_usd']):
                raise ValueError('campaign cap differs from authorized job cap')
            capture(job['cpus'], 'preflight', '--run', job['run'])
        batch.update(status='running', started_unix=time.time(), pid=os.getpid())
        def save():
            atomic_json(directory / 'batch.json', batch)
        def start(job):
            with (Path(job['run']) / 'builder-process.log').open('w') as log:
                return subprocess.Popen(command(job['cpus'], 'run', '--run', job['run'], '--key-file', key_file),
                                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        save()
        def stop(signum, frame):
            raise KeyboardInterrupt('batch interrupted')
        previous = signal.signal(signal.SIGTERM, stop)
        try:
            schedule(batch['jobs'], batch['parallel'], start, save)
        except BaseException:
            batch['status'] = 'interrupted'
            save()
            raise
        finally:
            signal.signal(signal.SIGTERM, previous)
        return finalize(directory, batch, Path(results).resolve())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare', help='Prepare isolated campaigns without model calls')
    prepare_parser.add_argument('--directory', type=Path, required=True)
    prepare_parser.add_argument('--stages', type=int, nargs='+', default=[1, 5, 10])
    prepare_parser.add_argument('--replicas', type=int, default=3)
    prepare_parser.add_argument('--parallel', type=int, default=3)
    budgets = prepare_parser.add_mutually_exclusive_group(required=True)
    budgets.add_argument('--budget-usd')
    budgets.add_argument('--budgets-usd', nargs='+', help='One independent run per stage, replica, and budget')
    prepare_parser.add_argument('--wall-seconds', type=int, default=7200)
    prepare_parser.add_argument('--language', choices=('cpp', 'rust'), default='cpp')
    for name in ('run', 'status', 'finalize'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--directory', type=Path, required=True)
        if name in ('run', 'finalize'):
            cmd.add_argument('--results', type=Path, default=ROOT / 'results')
        if name == 'run':
            cmd.add_argument('--key-file', type=Path, required=True)
    args = parser.parse_args(argv)
    values = vars(args).copy(); action = values.pop('command')
    try:
        if action == 'prepare':
            result = prepare(**values)
        elif action == 'run':
            result = launch(**values)
        elif action == 'finalize':
            with lock(args.directory):
                batch = read(args.directory / 'batch.json')
                if batch['status'] not in ('finalizing', 'completed_with_failures', 'complete'):
                    raise ValueError('finalize requires stopped builders; it never resumes model calls')
                result = finalize(args.directory, batch, args.results.resolve())
        else:
            result = read(args.directory / 'batch.json')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}))
        return 1
