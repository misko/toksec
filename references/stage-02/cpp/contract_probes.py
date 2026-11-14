#!/usr/bin/env python3
"""Independent Stage 2 black-box probes, using the normal candidate sandbox."""
import argparse
import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from toksec.wire import Wire, payload, request


def child(name):
    if name == 'max-requests-pipeline':
        with Wire() as wire:
            wire.send(request('/hello.txt', close=False) * 20)
            for i in range(3):
                response = wire.read()
                assert response.status == 200 and response.body == b'hello toksec\n'
                assert response.header('connection') == ('close' if i == 2 else 'keep-alive')
            assert wire.stream.read(1) == b'', 'expected orderly EOF after final response'
    elif name == 'half-close-large-output':
        with Wire(timeout=5) as wire:
            wire.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
            wire.send(request('/stall', close=False) + request('/stall', method='HEAD', close=False) + request('/data/4096', close=False))
            wire.socket.shutdown(socket.SHUT_WR)
            time.sleep(0.1)
            assert wire.read().body == payload(8 * 1024 * 1024)
            assert wire.read(head=True).header('content-length') == str(8 * 1024 * 1024)
            assert wire.read().body == payload(4096)
            assert wire.stream.read(1) == b''
    elif name == 'small-header-boundary-and-syntax':
        base = b'GET /hello.txt HTTP/1.1\r\nX: '
        for length, expected in ((128, 200), (129, 431)):
            with Wire() as wire:
                wire.send(base + b'x' * (length - len(base) - 4) + b'\r\n\r\n')
                assert wire.read().status == expected
        for header in (b'Bad Name: x', b': x', b'Content-Length: +0', b'Content-Length: 0,0',
                       b'Content-Length: \t', b'Content-Length: 0\r\ncOnTeNt-LeNgTh: 0',
                       b'Transfer-Encoding:', b'X: a\x00b', b'X: a\rb'):
            with Wire() as wire:
                wire.send(b'GET /hello.txt HTTP/1.1\r\n' + header + b'\r\n\r\n')
                assert wire.read().status == 400, repr(header)
        with Wire() as wire:
            wire.send(b'GET /hello.txt HTTP/1.1\r\nX: \xff\xfe\r\nContent-Length: \t0000\t\r\n\r\n')
            assert wire.read().body == b'hello toksec\n'
    elif name == 'decoded-path-and-parent-symlink':
        for target, status, body in (
            ('/data%2f4096', 200, payload(4096)), ('/data/./4096', 200, payload(4096)),
            ('//hello.txt', 200, b'hello toksec\n'), ('/%2568ello.txt', 404, b''),
            ('/inside-link/child', 403, b''), ('/escape/child', 403, b''),
            ('/data/%2E%2e/hello.txt', 403, b''), ('/data/%C0%AE', 400, b''),
            ('/%ED%A0%80', 400, b''), ('/%F4%90%80%80', 400, b''), ('/%E2%82', 400, b'')):
            with Wire() as wire:
                wire.send(request(target))
                response = wire.read()
                assert response.status == status, (target, response.status)
                assert response.body == body
    elif name == 'persistent-header-deadline':
        with Wire(timeout=2) as wire:
            wire.send(request('/empty', close=False))
            assert wire.read().body == b''
            time.sleep(0.2)
            start = time.monotonic()
            wire.send(b'GET /hello.txt HTTP/1.1\r\nX: ')
            for _ in range(5):
                time.sleep(0.08)
                try:
                    wire.send(b'x')
                except OSError:
                    break
            assert wire.socket.recv(4096) == b''
            elapsed = time.monotonic() - start
            assert elapsed < 0.65, elapsed
    elif name == 'unknown-method-malformed-target':
        for target in ('/%GG', 'http://alpha.test/hello.txt', '/%00', '/%ff', '/hello.txt#x'):
            with Wire() as wire:
                wire.send(request(target, method='DELETE'))
                assert wire.read().status == 400, target
        with Wire() as wire:
            wire.send(request('/hello.txt', method='CUSTOM'))
            assert wire.read().status == 405
    elif name == 'malformed-pipeline-preserves-prior-output':
        with Wire(timeout=5) as wire:
            wire.send(request('/large', close=False) + b'GET /hello.txt HTTP/1.1\r\nBad Name: x\r\n\r\n' + request('/empty'))
            assert wire.read().body == payload(2 * 1024 * 1024)
            assert wire.read().status == 400
            assert wire.stream.read(1) == b''
    elif name == 'cache-eviction-during-active-output':
        with Wire(timeout=5) as wire:
            wire.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)
            wire.send(request('/stall', close=False))
            time.sleep(0.05)
            for i in range(160):
                with Wire() as other:
                    other.send(request(f'/probe-{i}'))
                    assert other.read().body == payload(65536)
            assert wire.read().body == payload(8 * 1024 * 1024)
            wire.send(request('/hello.txt'))
            assert wire.read().body == b'hello toksec\n'
    else:
        raise ValueError(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child')
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    from toksec import sandbox
    from toksec.specification import configuration
    args.output.mkdir(parents=True, exist_ok=False)
    cases = []
    changes = {
        'max-requests-pipeline': {'max_requests': '3', 'pipeline_depth': '2'},
        'half-close-large-output': {'max_requests': '3', 'pipeline_depth': '1'},
        'small-header-boundary-and-syntax': {'header_bytes': '128'},
        'decoded-path-and-parent-symlink': {},
        'persistent-header-deadline': {'header_timeout_ms': '250', 'idle_timeout_ms': '1000'},
        'unknown-method-malformed-target': {},
        'malformed-pipeline-preserves-prior-output': {'pipeline_depth': '1'},
        'cache-eviction-during-active-output': {'write_timeout_ms': '5000'},
    }
    for name, overrides in changes.items():
        values = configuration(2)
        values.update(overrides)
        data = ''.join(f'{key}={value}\n' for key, value in values.items())
        started = time.monotonic()
        with sandbox.running(args.artifact.resolve(), 2, data) as runtime:
            if name == 'cache-eviction-during-active-output':
                for i in range(160):
                    (runtime['fixtures'] / 'www' / f'probe-{i}').write_bytes(payload(65536))
            command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials', '--',
                       '/usr/bin/python3', '-I', '-B', str(Path(__file__).resolve()), '--child', name]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        cases.append({'id': name, 'passed': result.returncode == 0, 'seconds': time.monotonic() - started,
                      'overrides': overrides, 'stdout': result.stdout, 'stderr': result.stderr})
    values = configuration(2)
    valid = ''.join(f'{key}={value}\n' for key, value in values.items())
    invalid = [('unknown-key', valid + 'other=1\n'), ('duplicate-key', valid + 'pipeline_depth=2\n')]
    for key in ('max_connections', 'header_bytes', 'header_timeout_ms', 'idle_timeout_ms',
                'write_timeout_ms', 'max_requests', 'pipeline_depth'):
        for value in ('0', '-1', '+1', '1.5', '18446744073709551616'):
            invalid.append((f'{key}={value}', valid.replace(f'{key}={values[key]}\n', f'{key}={value}\n')))
    for value in ('127.0.0.1:0', '127.0.0.1:65536', '127.0.0.1:+8080', '127.0.0.1:http', '999.1.1.1:8080'):
        invalid.append((f'listen={value}', valid.replace('listen=127.0.0.1:8080\n', f'listen={value}\n')))
    invalid.append(('relative-root', valid.replace('root=/www\n', 'root=www\n')))
    for name, data in invalid:
        started = time.monotonic()
        error = ''
        with sandbox.running(args.artifact.resolve(), 2, data) as runtime:
            try:
                code = runtime['process'].wait(timeout=2)
                passed = code != 0
            except subprocess.TimeoutExpired:
                passed = False
                error = 'invalid configuration did not exit within two seconds'
        cases.append({'id': f'configuration:{name}', 'passed': passed, 'seconds': time.monotonic() - started, 'error': error})
    result = {'source_sha256': hashlib.sha256((args.artifact / 'main.cpp').read_bytes()).hexdigest(),
              'artifact': str(args.artifact.resolve()), 'cases': cases, 'passed': all(case['passed'] for case in cases)}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
