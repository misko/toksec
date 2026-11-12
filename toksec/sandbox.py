import contextlib
import json
import os
import resource
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from toksec import fixtures
from toksec.specification import ROOT


def sandbox_info(fd):
    data = b''
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while len(data) < 4096:
            if not selector.select(3):
                raise TimeoutError('sandbox did not report its child PID')
            block = os.read(fd, 4096)
            if not block:
                raise RuntimeError('sandbox exited before reporting its child PID')
            data += block
            try:
                return json.loads(data)['child-pid']
            except json.JSONDecodeError:
                pass
    raise RuntimeError('invalid sandbox status')


def limits(memory_mib, cpu_seconds, files=16384):
    def apply():
        resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (files,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def base():
    command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
               '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
               '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    for path in ('/usr', '/lib', '/lib64', '/bin'):
        if Path(path).exists():
            command += ['--ro-bind', path, path]
    return command


def kill(process):
    if process is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def toolchain():
    return Path(subprocess.check_output(['rustc', '--print', 'sysroot'], text=True).strip())


def build(source, artifact, level, test=False):
    artifact = Path(artifact).resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
        raise ValueError('main.rs must be UTF-8 source of at most 1 MiB')
    (artifact / 'main.rs').write_text(source)
    with tempfile.TemporaryDirectory(prefix='toksec-build-') as temporary:
        output = Path(temporary)
        command = base() + ['--ro-bind', str(toolchain()), '/toolchain',
                            '--ro-bind', str(artifact), '/src', '--bind', str(output), '/out',
                            '--chdir', '/src', '--', '/toolchain/bin/rustc', '--sysroot', '/toolchain',
                            '--edition=2021', '-C', 'linker=/usr/bin/gcc', '-C', 'opt-level=3', '-C', 'debuginfo=0',
                            '/src/main.rs', '-o', '/out/server']
        if test:
            command.append('--test')
        if level == 5:
            command += ['-C', 'link-arg=-l:libssl.so.3', '-C', 'link-arg=-l:libcrypto.so.3', '-C', 'link-arg=-l:libz.so.1']
        started = time.monotonic()
        process = None
        timed_out = False
        with (output / 'compiler.log').open('wb') as log:
            try:
                process = subprocess.Popen(command, stdout=log, stderr=log, preexec_fn=limits(4096, 60), start_new_session=True)
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                kill(process)
        binary = output / 'server'
        success = not timed_out and process.returncode == 0 and binary.is_file() and not binary.is_symlink()
        report = {'passed': success, 'timeout': timed_out, 'seconds': time.monotonic() - started,
                  'diagnostics': (output / 'compiler.log').read_text(errors='replace')[-16000:],
                  'compiler': subprocess.check_output(['rustc', '--version'], text=True).strip(), 'test': test}
        if success:
            import shutil
            shutil.copyfile(binary, artifact / 'server')
            (artifact / 'server').chmod(0o555)
        (artifact / 'build.json').write_text(json.dumps(report, indent=2))
        (artifact / 'main.rs').chmod(0o444)
        return report


@contextlib.contextmanager
def running(artifact, level, configuration_override=None):
    artifact = Path(artifact).resolve()
    with tempfile.TemporaryDirectory(prefix='toksec-runtime-') as temporary:
        directory = Path(temporary)
        fixtures.create(directory, level)
        if configuration_override is not None:
            (directory / 'server.conf').write_text(configuration_override)
        read_fd, write_fd = os.pipe()
        process = None
        with (directory / 'server.log').open('wb') as log:
            try:
                command = base() + ['--info-fd', str(write_fd), '--ro-bind', str(artifact), '/candidate',
                                    '--ro-bind', str(directory), '/fixtures', '--ro-bind', str(directory / 'www'), '/www',
                                    '--chdir', '/candidate', '--', '/candidate/server', '--config', '/fixtures/server.conf']
                cpus = sorted(os.sched_getaffinity(0))
                def constrain():
                    limits(512, 1800)()
                    os.sched_setaffinity(0, {cpus[0]})
                process = subprocess.Popen(command, stdout=log, stderr=log, pass_fds=(write_fd,),
                                           preexec_fn=constrain, start_new_session=True)
                os.close(write_fd)
                write_fd = None
                pid = sandbox_info(read_fd)
                yield {'process': process, 'pid': pid, 'fixtures': directory, 'cpu': cpus[0]}
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
                kill(process)


def invoke_driver(artifact, level, mode='check', **options):
    with running(artifact, level) as runtime:
        command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials',
                   '--', '/usr/bin/python3', '-I', '-B', str(ROOT / 'toksec/driver.py'),
                   '--level', str(level), '--fixtures', str(runtime['fixtures']), '--pid', str(runtime['pid']),
                   '--mode', mode, '--server-cpu', str(runtime['cpu'])]
        for key, value in options.items():
            command += ['--' + key.replace('_', '-'), str(value)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        try:
            output, errors = process.communicate(timeout=1800)
            if process.returncode:
                raise RuntimeError('trusted driver failed: ' + errors[-2000:])
            return json.loads(output)
        finally:
            kill(process)


def self_test(artifact):
    command = base() + ['--ro-bind', str(Path(artifact).resolve()), '/candidate', '--', '/candidate/server', '--test-threads=1']
    process = None
    with tempfile.TemporaryFile() as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=log, preexec_fn=limits(512, 30), start_new_session=True)
            code = process.wait(timeout=35)
        except subprocess.TimeoutExpired:
            code = -1
        finally:
            kill(process)
        log.seek(0)
        return {'passed': code == 0, 'output': log.read(16000).decode(errors='replace')}


def configuration_check(artifact, level):
    from toksec.specification import configuration
    values = configuration(level)
    valid = ''.join(f'{k}={v}\n' for k, v in values.items())
    variants = [valid + 'unknown=true\n', valid + 'root=/www\n',
                valid.replace('root=/www\n', ''), valid.replace('root=/www\n', 'root=/absent\n'),
                valid.replace('header_bytes=8192\n', 'header_bytes=0\n')]
    started = time.monotonic()
    try:
        for data in variants:
            with running(artifact, level, data) as runtime:
                try:
                    code = runtime['process'].wait(timeout=2)
                except subprocess.TimeoutExpired:
                    raise AssertionError('invalid configuration did not exit within two seconds')
                assert code != 0, 'invalid configuration exited successfully'
        return {'id': 'configuration', 'passed': True, 'seconds': time.monotonic() - started}
    except (AssertionError, RuntimeError, OSError) as error:
        return {'id': 'configuration', 'passed': False, 'seconds': time.monotonic() - started, 'error': str(error)}


def evaluate(artifact, level):
    result = invoke_driver(artifact, level)
    config = configuration_check(artifact, level)
    result['cases'].append(config)
    result['passed'] &= config['passed']
    return result
