#!/usr/bin/env python3
"""Run a complete trusted diagnostic and its server children in one sandbox."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toksec import sandbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New writable directory under .runs/references')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='-- Python diagnostic script and its arguments')
    args = parser.parse_args()
    arguments = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not arguments:
        parser.error('a Python diagnostic script is required')
    script = Path(arguments[0]).resolve()
    output = args.output.resolve()
    if not script.is_file() or not script.is_relative_to(ROOT):
        parser.error('diagnostic script must be a file inside the repository')
    if not output.is_relative_to(ROOT / '.runs/references') or output == ROOT / '.runs/references':
        parser.error('output must be a new child directory of .runs/references')
    output.mkdir(parents=True, exist_ok=False)
    command = sandbox.base() + ['--ro-bind', str(ROOT), str(ROOT), '--bind', str(output), str(output),
                                '--chdir', str(ROOT), '--', '/usr/bin/python3', str(script), *arguments[1:]]
    process = None
    timed_out = False
    with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       preexec_fn=sandbox.limits(512, 120), start_new_session=True)
            process.wait(timeout=150)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            sandbox.kill(process)
    report = {'sandboxed': True, 'returncode': process.returncode if process else None, 'timeout': timed_out,
              'script': str(script.relative_to(ROOT)), 'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
              'arguments': arguments[1:], 'writable_output': str(output),
              'limits': {'address_space_mib': 512, 'cpu_seconds': 120, 'file_descriptors': 16384}}
    (output / 'sandbox.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if not timed_out and process and process.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
