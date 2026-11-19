#!/usr/bin/env python3
"""Adopt live batch workers and schedule unstarted jobs under one global limit."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.storage import atomic_json


def read(path):
    return json.loads(Path(path).read_text())


def ready_job(job, manifest):
    if job['status'] != 'prepared' or manifest['started_unix'] is not None:
        raise ValueError('only never-started jobs may be launched')


def process_args(pid):
    return Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')


def command(root, cpus, *args):
    return ['taskset', '-c', ','.join(map(str, cpus)), sys.executable,
            str(root / 'scripts/run_parallel.py'), *map(str, args)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, action='append', required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--parallel', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.parallel <= 4:
        parser.error('parallel must be between one and four')
    groups = [list(range(n, n + 6)) for n in range(0, 24, 6)]
    if not set(sum(groups, [])) <= os.sched_getaffinity(0):
        parser.error('this coordinator requires CPUs 0 through 23')
    args.state.parent.mkdir(parents=True, exist_ok=True)
    coordinator_lock = args.state.with_suffix('.lock').open('a')
    fcntl.flock(coordinator_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.state.exists():
        parser.error('coordinator state already exists; inspect it before any recovery')
    batches = []
    for directory in args.batch:
        directory = directory.resolve(); data = read(directory / 'batch.json')
        if data['status'] != 'running':
            parser.error('only running batch supervisors can be adopted')
        pid = data['pid']; argv = process_args(pid)
        if str(directory).encode() not in argv or b'run' not in argv:
            parser.error('supervisor process identity differs from recorded batch')
        batches.append({'directory': directory, 'data': data, 'old_pid': pid,
                        'root': Path(os.readlink(f'/proc/{pid}/cwd'))})
    paused = []; handles = []; active = {}; processes = []
    committed = False
    def save():
        for batch in batches:
            atomic_json(batch['directory'] / 'batch.json', batch['data'])
        atomic_json(args.state, {'pid': os.getpid(), 'parallel': args.parallel,
                    'active': [{'pid': pid, 'job': job['id'], 'cpus': job['cpus']}
                               for pid, (_, _, job) in active.items()],
                    'batches': [str(b['directory']) for b in batches]})
    try:
        for batch in batches:
            os.kill(batch['old_pid'], signal.SIGSTOP); paused.append(batch['old_pid'])
        # Wait until supervisors cannot change queues, without stopping their children.
        for pid in paused:
            deadline = time.monotonic() + 5
            while Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'T':
                if time.monotonic() > deadline: raise RuntimeError('supervisor did not stop')
                time.sleep(.02)
        occupied = set()
        for batch in batches:
            batch['data'] = read(batch['directory'] / 'batch.json')
            if batch['data']['status'] != 'running':
                raise RuntimeError('batch began finalizing during takeover; retry later')
            for job in batch['data']['jobs']:
                if job['status'] == 'starting':
                    raise RuntimeError('job is between launch states; retry takeover')
                if job['status'] == 'running':
                    pid = job['pid']
                    if job['run'].encode() not in process_args(pid):
                        raise RuntimeError('worker identity mismatch')
                    if occupied.intersection(job['cpus']): raise RuntimeError('workers overlap CPUs')
                    occupied.update(job['cpus'])
                    fd = os.pidfd_open(pid); active[pid] = (fd, batch, job)
            for job in batch['data']['jobs']:
                if job['status'] == 'prepared': ready_job(job, read(Path(job['run']) / 'manifest.json'))
        if len(active) > args.parallel: raise RuntimeError('more active workers than requested limit')
        atomic_json(args.state.with_suffix('.handoff.json'), {
            'old_supervisors': paused, 'new_supervisor': os.getpid(),
            'original_batches': [b['data'] for b in batches]})
        # Kill only the stopped queue supervisors. Workers have separate sessions.
        # SIGTERM would invoke the old supervisors' worker-cancellation handlers.
        for pid in paused: os.kill(pid, signal.SIGKILL)
        committed = True
        for batch in batches:
            stream = (batch['directory'] / 'batch.lock').open('a')
            fcntl.flock(stream, fcntl.LOCK_EX); handles.append(stream)
            batch['data'].update(pid=os.getpid(), coordinator=str(args.state),
                                 previous_supervisor_pid=batch['old_pid'])
        save()
        while active or any(j['status'] == 'prepared' for b in batches for j in b['data']['jobs']):
            busy = {cpu for _, _, j in active.values() for cpu in j['cpus']}
            for batch in batches:
                for job in batch['data']['jobs']:
                    if len(active) >= args.parallel: break
                    if job['status'] != 'prepared': continue
                    cpus = next((g for g in groups if not busy.intersection(g)), None)
                    if cpus is None: break
                    run = Path(job['run']); manifest = read(run / 'manifest.json')
                    ready_job(job, manifest)
                    # Retain preparation CPU provenance; only execution placement changes.
                    original = run / 'manifest.before-coordination.json'
                    if original.exists(): raise RuntimeError('job already has a coordination record')
                    atomic_json(original, manifest)
                    if job['stage'] == 10: manifest['cpus'] = cpus[:1]
                    else: manifest['cpu_affinity'] = cpus
                    manifest['execution_placement'] = {'coordinator': str(args.state), 'cpus': cpus,
                                                       'prepared_manifest': original.name,
                                                       'prepared_cpus': read(original).get('cpus', read(original).get('cpu_affinity'))}
                    atomic_json(run / 'manifest.json', manifest)
                    job.update(cpus=cpus, slot=groups.index(cpus), status='starting')
                    save()
                    with (run / 'builder-process.log').open('a') as log:
                        process = subprocess.Popen(['taskset', '-c', ','.join(map(str, cpus)),
                            sys.executable, '-m', 'toksec', 'run', '--run', str(run),
                            '--key-file', str(args.key_file)], cwd=batch['root'],
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    processes.append(process)
                    active[process.pid] = (os.pidfd_open(process.pid), batch, job)
                    job.update(status='running', pid=process.pid, started_unix=time.time())
                    busy.update(cpus);save()
            for pid, (fd, batch, job) in list(active.items()):
                if select.select([fd], [], [], 0)[0]:
                    job.update(status='builder_stopped', ended_unix=time.time())
                    os.close(fd);del active[pid];save()
            for process in processes: process.poll()
            time.sleep(1)
        for stream in handles: stream.close()
        handles.clear()
        for batch in batches:
            batch['data']['status'] = 'finalizing'
            atomic_json(batch['directory'] / 'batch.json', batch['data'])
            with (batch['directory'] / 'coordinated-finalization.log').open('a') as log:
                result = subprocess.run(command(batch['root'], list(range(24)), 'finalize',
                    '--directory', batch['directory'], '--results', args.results), cwd=batch['root'],
                    stdout=log, stderr=subprocess.STDOUT)
            batch['data'] = read(batch['directory'] / 'batch.json')
            batch['data']['coordinator_finalize_exit'] = result.returncode
        save()
    finally:
        if not committed:
            for pid in paused:
                try: os.kill(pid, signal.SIGCONT)
                except ProcessLookupError: pass
        for stream in handles: stream.close()
        for fd, _, _ in active.values(): os.close(fd)


if __name__ == '__main__':
    main()
