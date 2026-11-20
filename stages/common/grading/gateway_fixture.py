"""Build the fixed, parent-owned throughput fixture outside the candidate mount."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).with_name("probes") / "gateway_load_origin.cpp"


def binary(tool='origin'):
    sources = {'origin': SOURCE, 'client': SOURCE.with_name('gateway_client.cpp')}
    source = sources[tool]
    compiler = subprocess.check_output(['/usr/bin/g++', '--version'])
    digest = hashlib.sha256(source.read_bytes() + compiler).hexdigest()
    directory = Path.home() / '.cache' / 'toksec' / 'benchmark-tools'
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = directory / (tool + '-' + digest)
    if not path.is_file():
        with tempfile.TemporaryDirectory(dir=directory) as build:
            output = Path(build) / tool
            subprocess.run(['/usr/bin/g++', '-std=c++20', '-O3', '-pipe', str(source), '-o', str(output)],
                           check=True, timeout=60, env={**os.environ, 'TMPDIR': build})
            os.replace(output, path)
    return path
