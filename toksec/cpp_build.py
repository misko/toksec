import functools
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


@functools.lru_cache(maxsize=1)
def allowed_headers():
    major = subprocess.check_output(['g++', '-dumpversion'], text=True).strip().split('.')[0]
    packages = ['libc6-dev', 'linux-libc-dev', f'libstdc++-{major}-dev', f'libgcc-{major}-dev']
    listing = subprocess.check_output(['dpkg-query', '-L', *packages], text=True)
    return {str(Path(line).resolve()) for line in listing.splitlines() if line.startswith('/') and Path(line).is_file()}


def inspect(output):
    dependencies = (output / 'headers.d').read_text().replace('\\\n', ' ')
    files = shlex.split(dependencies.split(':', 1)[1])
    forbidden = [p for p in files if p not in ('/src/main.cpp', 'main.cpp') and str(Path(p).resolve()) not in allowed_headers()]
    if forbidden:
        return 'Unapproved headers: ' + ', '.join(forbidden[:10])
    from toksec.binary_policy import inspect_binary
    return inspect_binary(output / 'server')


def build(source, artifact, level, test=False):
    from toksec.sandbox import base, limits, kill
    from toksec.languages import profile
    profile('cpp', level)
    artifact = Path(artifact).resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
        raise ValueError('main.cpp must be UTF-8 source of at most 1 MiB')
    (artifact/'main.cpp').write_text(source)
    with tempfile.TemporaryDirectory(prefix='toksec-cpp-build-') as temporary:
        output = Path(temporary)
        command = base() + ['--ro-bind', str(artifact), '/src', '--bind', str(output), '/out', '--chdir', '/src', '--',
                            '/usr/bin/g++', '-std=c++20', '-O3', '-pthread', '-MD', '-MF', '/out/headers.d']
        if not test:
            command.append('-DNDEBUG')
        command += ['/src/main.cpp', '-o', '/out/server']
        started = time.monotonic()
        process = None
        timed_out = False
        with (output/'compiler.log').open('wb') as log:
            try:
                process = subprocess.Popen(command, stdout=log, stderr=log, preexec_fn=limits(4096, 60), start_new_session=True)
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                kill(process)
        binary = output/'server'
        success = not timed_out and process.returncode == 0 and binary.is_file() and not binary.is_symlink()
        diagnostics = (output/'compiler.log').read_text(errors='replace')[-16000:]
        if success:
            violation = inspect(output)
            if violation:
                diagnostics += '\n' + violation
                success = False
        report = {'passed': success, 'timeout': timed_out, 'seconds': time.monotonic()-started,
                  'diagnostics': diagnostics, 'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                  'language': 'cpp', 'test': test}
        if success:
            shutil.copyfile(binary, artifact/'server')
            (artifact/'server').chmod(0o555)
        (artifact/'build.json').write_text(json.dumps(report, indent=2))
        (artifact/'main.cpp').chmod(0o444)
        return report
