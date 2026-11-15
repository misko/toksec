"""Stage 10 isolation. cgroup v2 enforces tree resources; RLIMIT is supplementary.

TasksMax includes threads and bubblewrap's supervisor: workers+2 tasks, with
floor(16384 / (workers+2)) FDs per task, imply an aggregate FD bound <=16384.
Configured workers are limited to four; TasksMax is the kernel bound (it cannot
distinguish workers from other processes). Extra threads consume that same task
budget. No legacy policy is modified by this OpenSSL-specific build profile.
"""
import contextlib
import functools
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from toksec.sandbox import base, server_pid, toolchain

MEMORY = 512 * 1024 * 1024
SCRATCH = 64 * 1024 * 1024
TASKS = 16
FILES = 16384 // TASKS


def _base():
    command = base()
    index = command.index('--tmpfs')
    command[index:index] = ['--size', str(SCRATCH)]
    # /dev is its own tmpfs; disallow storing arbitrary files there.
    return command + ['--as-pid-1', '--remount-ro', '/dev']


def _systemctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], check=check,
                          capture_output=True, text=True, timeout=10)


def _verify_cgroup(path, memory, tasks):
    root = Path('/sys/fs/cgroup') / path.lstrip('/')
    expected = {'memory.max': str(memory), 'memory.swap.max': '0',
                'pids.max': str(tasks)}
    for name, value in expected.items():
        if (root / name).read_text().strip() != value:
            raise RuntimeError('aggregate resource containment unavailable: ' + name)
    quota, period = (root / 'cpu.max').read_text().split()
    if quota == 'max' or int(quota) > int(period):
        raise RuntimeError('aggregate one-CPU containment unavailable')
    return root


@contextlib.contextmanager
def _unit(command, log, *, memory=MEMORY, tasks=TASKS, timeout=1800,
          cpus=None, files=FILES):
    """Stop a trusted launcher, verify kernel limits, then allow execution."""
    name = 'toksec-stage10-' + uuid.uuid4().hex + '.service'
    cpus = tuple(sorted(os.sched_getaffinity(0)))[:1] if cpus is None else tuple(cpus)
    if not cpus or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError('cpus must be a nonempty subset of allowed CPUs')
    properties = {'MemoryMax': memory, 'MemorySwapMax': 0, 'CPUQuota': '100%',
                  'TasksMax': tasks, 'LimitNOFILE': files, 'LimitCORE': 0,
                  'LimitFSIZE': SCRATCH, 'RuntimeMaxSec': timeout,
                  'KillMode': 'control-group', 'TimeoutStopSec': 1,
                  'SendSIGKILL': 'yes',
                  'MemoryAccounting': 'yes', 'TasksAccounting': 'yes'}
    launch = ['systemd-run', '--user', '--quiet', '--wait', '--pipe', '--expand-environment=no', '--collect', '--unit', name]
    for key, value in properties.items():
        launch += ['--property', f'{key}={value}']
    # The service manager applies limits, and the host independently verifies
    # cgroup files while this trusted shell is stopped, before candidate code.
    launch += ['/bin/sh', '-c', 'kill -STOP $$; exec "$@"', 'stage10-launch',
               '/usr/bin/taskset', '-c', ','.join(map(str, cpus)), *command]
    process = None
    try:
        process = subprocess.Popen(launch, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('user-systemd containment launcher failed')
            result = _systemctl('show', name, '-p', 'MainPID', '-p', 'ControlGroup', check=False)
            values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            pid = int(values.get('MainPID', '0'))
            if pid:
                try:
                    stopped = re.search(r'^State:\s+T', Path(f'/proc/{pid}/status').read_text(), re.M)
                except FileNotFoundError:
                    stopped = False
                if stopped:
                    cgroup = _verify_cgroup(values['ControlGroup'], memory, tasks)
                    os.kill(pid, signal.SIGCONT)
                    yield {'process': process, 'supervisor_pid': pid, 'cgroup': cgroup,
                           'cpu': cpus[0], 'cpus': cpus, 'unit': name}
                    return
            time.sleep(.02)
        raise RuntimeError('resource containment startup timed out')
    finally:
        # Stop the entire service cgroup, including daemonized descendants.
        _systemctl('stop', name, check=False)
        if process is not None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def inspect_binary(binary, test=False):
    dynamic = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    needed = set(re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic))
    allowed = {'ld-linux-x86-64.so.2', 'ld-linux-aarch64.so.1', 'libstdc++.so.6',
               'libc.so.6', 'libm.so.6', 'libgcc_s.so.1', 'libpthread.so.0', 'librt.so.1',
               'libssl.so.3', 'libcrypto.so.3'}
    if needed - allowed:
        return 'Unapproved linked libraries: ' + ', '.join(sorted(needed - allowed))
    symbols = subprocess.check_output(['nm', '-u', str(binary)], text=True)
    if re.search(r'\b(dlopen|dlmopen|dlsym|dlvsym)(@|\s|$)', symbols):
        return 'Runtime library loading is not permitted'
    return None


@functools.lru_cache(maxsize=1)
def allowed_headers():
    from toksec.cpp_build import allowed_headers as legacy_headers
    listing = subprocess.check_output(['dpkg-query', '-L', 'libssl-dev'], text=True)
    return legacy_headers() | {str(Path(p).resolve()) for p in listing.splitlines()
                               if p.startswith('/') and Path(p).is_file()}


def build(source, artifact, language='rust', test=False):
    if language not in ('rust', 'cpp'):
        raise ValueError('language must be rust or cpp')
    if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
        raise ValueError('source must be UTF-8 text of at most 1 MiB')
    artifact = Path(artifact).resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    filename = 'main.cpp' if language == 'cpp' else 'main.rs'
    (artifact / filename).write_text(source)
    with tempfile.TemporaryDirectory(prefix='stage10-build-') as temporary:
        output = Path(temporary)
        command = _base() + ['--ro-bind', str(artifact), '/src', '--bind', str(output), '/out', '--chdir', '/src']
        if language == 'cpp':
            command += ['--', '/usr/bin/g++', '-std=c++20', '-O3', '-pthread', '-MD', '-MF', '/out/headers.d']
            if not test:
                command += ['-DNDEBUG']
            command += ['/src/main.cpp', '-o', '/out/server', '-lssl', '-lcrypto']
        else:
            command += ['--ro-bind', str(toolchain()), '/toolchain', '--', '/toolchain/bin/rustc',
                        '--sysroot', '/toolchain', '--edition=2021', '-C', 'linker=/usr/bin/gcc',
                        '-C', 'opt-level=3', '-C', 'debuginfo=0', '/src/main.rs', '-o', '/out/server',
                        '-l', 'ssl', '-l', 'crypto']
            if test:
                command += ['-C', 'debug-assertions=yes']
        started = time.monotonic()
        timed_out = False
        with (output / 'compiler.log').open('wb') as log:
            with _unit(command, log, memory=4096 * 1024**2, tasks=64, files=256, timeout=120) as runtime:
                try:
                    code = runtime['process'].wait(timeout=125)
                except subprocess.TimeoutExpired:
                    code = -1
                    timed_out = True
        binary = output / 'server'
        success = code == 0 and binary.is_file() and not binary.is_symlink()
        diagnostics = (output / 'compiler.log').read_text(errors='replace')[-16000:]
        if success:
            violation = inspect_binary(binary, test)
            if language == 'cpp':
                dependencies = (output / 'headers.d').read_text().replace('\\\n', ' ')
                headers = shlex.split(dependencies.split(':', 1)[1])
                forbidden = [p for p in headers if p not in ('/src/main.cpp', 'main.cpp')
                             and str(Path(p).resolve()) not in allowed_headers()]
                if forbidden:
                    violation = 'Unapproved headers: ' + ', '.join(forbidden[:10])
            if violation:
                diagnostics += '\n' + violation
                success = False
        report = {'passed': success, 'timeout': timed_out, 'seconds': time.monotonic()-started,
                  'diagnostics': diagnostics, 'language': language, 'test': test,
                  'compiler': subprocess.check_output(['g++' if language == 'cpp' else 'rustc', '--version'], text=True).splitlines()[0]}
        if success:
            shutil.copyfile(binary, artifact / 'server')
            (artifact / 'server').chmod(0o555)
        (artifact / filename).chmod(0o444)
        (artifact / 'build.json').write_text(json.dumps(report, indent=2))
        return report


@contextlib.contextmanager
def running(artifact, fixtures, cpus=None, workers=2, timeout=1800, args=None, wait_for_pid=True):
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 4:
        raise ValueError('workers must be between 1 and 4')
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    artifact, fixtures = Path(artifact).resolve(), Path(fixtures).resolve()
    for name in ('config', 'tls', 'www'):
        path = fixtures / name
        if not path.exists() or path.is_symlink():
            raise ValueError('missing or symlinked fixture: ' + name)
    with tempfile.TemporaryDirectory(prefix='stage10-runtime-') as temporary:
        log_path = Path(temporary) / 'server.log'
        command = _base() + ['--dir', '/candidate', '--ro-bind', str(artifact / 'server'), '/candidate/server',
                            '--dir', '/fixtures', '--ro-bind', str(fixtures / 'config'), '/fixtures/config',
                            '--ro-bind', str(fixtures / 'tls'), '/fixtures/tls',
                            '--ro-bind', str(fixtures / 'www'), '/www',
                            '--symlink', '/fixtures/tls', '/tls', '--chdir', '/candidate',
                            '--remount-ro', '/', '--', '/candidate/server']
        command += ['--config', '/fixtures/config/nginx.conf'] if args is None else list(args)
        with log_path.open('wb') as log:
            with _unit(command, log, timeout=timeout, cpus=cpus, tasks=workers+2, files=16384//(workers+2)) as runtime:
                runtime.update(fixtures=fixtures, log=log_path,
                               limits={'memory_bytes': MEMORY, 'cpu_quota': 1, 'tasks': workers+2,
                                       'files_per_process': 16384//(workers+2),
                                       'aggregate_fd_upper_bound': (workers+2)*(16384//(workers+2)),
                                       'extra_threads': 'consume the same task budget as processes',
                                       'scratch_bytes': SCRATCH, 'configured_workers': workers})
                if wait_for_pid:
                    runtime['pid'] = server_pid(runtime['supervisor_pid'], artifact)
                yield runtime


def self_test(artifact, fixtures, language='rust', timeout=35):
    args = ['--run-tests']
    with running(artifact, fixtures, timeout=timeout, args=args, wait_for_pid=False) as runtime:
        try:
            code = runtime['process'].wait(timeout=timeout+5)
        except subprocess.TimeoutExpired:
            code = -1
        return {'passed': code == 0, 'exit_code': code,
                'output': runtime['log'].read_text(errors='replace')[-16000:]}
