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


def server_pid(namespace_pid, artifact, timeout=3):
    """Resolve the executable below bwrap's namespace supervisor, not the supervisor."""
    expected = (Path(artifact) / 'server').stat()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pending = [namespace_pid]
        while pending:
            pid = pending.pop()
            try:
                actual = Path(f'/proc/{pid}/exe').stat()
                if (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino):
                    return pid
                pending.extend(int(x) for x in Path(f'/proc/{pid}/task/{pid}/children').read_text().split())
            except (OSError, ValueError):
                pass
        time.sleep(.01)
    raise RuntimeError('server executable not found under sandbox supervisor')


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


def build(source, artifact, level, test=False, language='rust'):
    from toksec.languages import profile
    profile(language, level)
    if level == 15:
        from toksec.sandbox import cgroup
        return cgroup.build(source, artifact, language, test)
    if language == 'cpp':
        from toksec.cpp_build import build as cpp_build
        return cpp_build(source, artifact, level, test)
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
            from toksec.binary_policy import inspect_binary
            violation = inspect_binary(binary, allow_test_runtime_symbols=test)
            if violation:
                report['diagnostics'] += '\n' + violation
                report['passed'] = success = False
        if success:
            import shutil
            shutil.copyfile(binary, artifact / 'server')
            (artifact / 'server').chmod(0o555)
        (artifact / 'build.json').write_text(json.dumps(report, indent=2))
        (artifact / 'main.rs').chmod(0o444)
        return report


@contextlib.contextmanager
def running(artifact, level, configuration_override=None, smoke=False):
    artifact = Path(artifact).resolve()
    with tempfile.TemporaryDirectory(prefix='toksec-runtime-') as temporary, tempfile.TemporaryDirectory(prefix='toksec-parent-') as private:
        directory = Path(temporary)
        (fixtures.create_smoke if smoke else fixtures.create)(directory, level)
        if level == 15:
            from stages.common.grading.gateway_origin import issue_certificates
            issue_certificates(Path(private), directory)
        if configuration_override is not None:
            (directory / 'server.conf').write_text(configuration_override)
        read_fd, write_fd = os.pipe()
        process = None
        with (directory / 'server.log').open('wb') as log:
            try:
                command = base() + ['--info-fd', str(write_fd), '--ro-bind', str(artifact), '/candidate',
                                    '--ro-bind', str(directory), '/fixtures', '--ro-bind', str(directory / 'www'), '/www',
                                    *(['--size', str(384 * 1024**2), '--tmpfs', '/tmp/spool'] if level == 16 else []),
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
                yield {'process': process, 'pid': pid, 'fixtures': directory, 'private': private, 'cpu': cpus[0]}
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
                kill(process)


def invoke_driver(artifact, level, mode='check', configuration_override=None, **options):
    if mode == 'benchmark' and level == 5 and configuration_override is None:
        from toksec.specification import configuration
        values = configuration(level)
        values['cache_ttl_ms'] = '60000'
        configuration_override = ''.join(f'{k}={v}\n' for k, v in values.items())
    if mode == 'benchmark' and level in (12, 13, 14, 16) and configuration_override is None:
        from toksec.specification import configuration
        values = configuration(level)
        if level == 14:
            values.update(client_burst='10000000', global_burst='10000000')
        elif level == 16:
            values.update(tenant_bytes='268435456', spool_bytes='268435456', upload_timeout_ms='2000')
        else:
            values.update(cache_ttl_ms='60000')
        configuration_override = ''.join(f'{k}={v}\n' for k,v in values.items())
    with running(artifact, level, configuration_override, smoke=options.get('suite') == 'smoke' or mode == 'benchmark') as runtime:
        command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials',
                   '--', '/usr/bin/python3', '-I', '-B', str(ROOT / 'toksec/driver.py'),
                   '--stage', str(level), '--fixtures', str(runtime['fixtures']), '--pid', str(server_pid(runtime['pid'], artifact)),
                   '--private', runtime['private'], '--mode', mode, '--server-cpu', str(runtime['cpu'])]
        for key, value in options.items():
            command += ['--' + key.replace('_', '-'), str(value)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        try:
            output, errors = process.communicate(timeout=1800)
            if process.returncode:
                raise RuntimeError('trusted driver failed: ' + errors[-2000:] + '\nServer diagnostics: ' +
                                   (runtime['fixtures'] / 'server.log').read_text(errors='replace')[-4000:])
            result = json.loads(output)
            if mode == 'check':
                result['server_diagnostics'] = (runtime['fixtures'] / 'server.log').read_text(errors='replace')[-4000:]
                result['server_exit_code'] = runtime['process'].poll()
            return result
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
                valid.replace('header_bytes=8192\n', 'header_bytes=0\n'),
                valid.replace('root=/www\n', 'root=/www/hello.txt\n'),
                valid.replace('root=/www\n', 'root=/www/pipe\n')]
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


def evaluate(artifact, level, smoke=False):
    if smoke:
        result = invoke_driver(artifact, level, suite='smoke')
        result['evaluation_scope'] = 'visible_smoke_only'
        return result
    result = invoke_driver(artifact, level)
    config = configuration_check(artifact, level)
    from toksec.checks import configured_cases
    from toksec.specification import configuration
    for check in configured_cases(level):
        from toksec.stages import module as stage_module
        CONFIGURATIONS = stage_module(2, 'api').CONFIGURATIONS
        values = configuration(level)
        values.update(CONFIGURATIONS[check.id])
        data = ''.join(f'{k}={v}\n' for k, v in values.items())
        try:
            extra = invoke_driver(artifact, level, case=check.id, configuration_override=data)
            result['cases'].extend(extra['cases'])
            result['passed'] &= extra['passed']
        except Exception as error:
            result['cases'].append({'id': check.id, 'passed': False, 'error': str(error)[:1000]})
            result['passed'] = False
    result['cases'].append(config)
    result['passed'] &= config['passed']
    return result
