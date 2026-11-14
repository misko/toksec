#!/usr/bin/env python3
"""Additional Stage 1 correctness diagnostics, using the existing runtime sandbox.

Run from the repository root with --artifact <compiled-candidate-dir> --output
<new-directory>. This deliberately performs no throughput measurement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from toksec import sandbox
from toksec.wire import Wire, request


def inside(custom=False):
    results = []

    def case(name, function):
        start = time.monotonic()
        try:
            function()
            results.append(dict(id=name, passed=True, seconds=time.monotonic() - start))
        except Exception as error:
            results.append(dict(id=name, passed=False, seconds=time.monotonic() - start,
                                error=f'{type(error).__name__}: {error}'))

    def exchange(raw, status=200, body=None, half_close=False):
        with Wire(port=8089 if custom else 8080, timeout=2) as wire:
            wire.send(raw)
            if half_close:
                wire.socket.shutdown(socket.SHUT_WR)
            response = wire.read()
            assert response.status == status, (response.status, status, raw[:100])
            if body is not None:
                assert response.body == body
            assert response.header('connection').lower() == 'close'
            assert wire.stream.read(1) == b''

    if custom:
        case('custom-listen-root-and-config-whitespace',
             lambda: exchange(request('/index.html'), body=b'<p>index</p>\n'))

        def header_limit():
            base = b'GET /index.html HTTP/1.1\r\nX: '
            for length, status in ((128, 200), (129, 431)):
                exchange(base + b'a' * (length - len(base) - 4) + b'\r\n\r\n', status)
        case('custom-128-byte-header-limit', header_limit)

        def deadline():
            with Wire(port=8089, timeout=1) as wire:
                start = time.monotonic()
                assert wire.socket.recv(1) == b''
                assert .05 < time.monotonic() - start < .3
        case('custom-90-ms-silent-deadline', deadline)
        print(json.dumps(dict(passed=all(item['passed'] for item in results), cases=results)))
        return

    case('http11-host-optional', lambda: exchange(request(host=None), body=b'hello toksec\n'))
    case('request-half-close', lambda: exchange(request(), body=b'hello toksec\n', half_close=True))

    def framing():
        for value in ('+0', '-0', '0, 0', '', '0x0', '0 0', '18446744073709551616'):
            exchange(request(headers={'Content-Length': value}), 400)
        for value in ('0', '\t000000\t', '0' * 1000):
            exchange(request(headers={'cOnTeNt-LeNgTh': value}), body=b'hello toksec\n')
        exchange(b'GET /hello.txt HTTP/1.1\r\nContent-Length: 0\r\nCONTENT-LENGTH: 0\r\n\r\n', 400)
        exchange(request(headers={'tRaNsFeR-EnCoDiNg': 'identity'}), 400)
        exchange(request(headers={'Content-Length': '8192'}, body=b'x' * 8192), 400)
    case('extended-framing', framing)

    def syntax():
        for raw in (b'G(ET /hello.txt HTTP/1.1\r\n\r\n',
                    b'GET\t/hello.txt HTTP/1.1\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1 EXTRA\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1\r\nX : bad\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1\r\nX: bad\x7f\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1\r\nX: bad\x01\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1\rX: bad\r\n\r\n',
                    b'GET /hello.txt HTTP/1.1\r\n\tX: bad\r\n\r\n'):
            exchange(raw, 400)
        for method in ('HEAD', 'POST', 'get', 'EXTENSION!'):
            exchange(request(method=method), 405)
        exchange(request(headers={'X': '\tallowed\t'}), body=b'hello toksec\n')
    case('extended-syntax', syntax)

    def paths():
        for path, body in (('/%E2%98%83.txt', b'unicode\n'),
                           ('/%252e%252e', b'one pass\n'),
                           ('/question%3Fmark', b'question\n'),
                           ('/hash%23mark', b'hash\n'),
                           ('//directory//../hello.txt', None)):
            exchange(request(path), 403 if body is None else 200, body)
        for path in ('/%C0%AF', '/%ED%A0%80', '/%F4%90%80%80', '/%E2%98',
                     '/hello.txt?x=#fragment', 'hello.txt', '*', '/%5Cfoo'):
            exchange(request(path), 400)
        exchange(request('/./hello.txt'), body=b'hello toksec\n')
        exchange(request('//hello.txt'), body=b'hello toksec\n')
    case('utf8-and-once-decoding', paths)

    def confinement():
        for path in ('/linked-directory/index.html', '/linked-missing/file',
                     '/unix-socket', '/directory/.', '/directory//', '/pipe'):
            exchange(request(path), 403)
        exchange(request('/hello.txt/child'), 404)
    case('extended-confinement', confinement)

    def deadlines():
        with Wire(timeout=2) as silent, Wire(timeout=2) as trickle:
            start = time.monotonic()
            trickle.send(b'GET /hello.txt HTTP/1.1\r\nX: ')
            for _ in range(4):
                time.sleep(.15)
                trickle.send(b'a')
                exchange(request(), body=b'hello toksec\n')
            for wire in (silent, trickle):
                wire.socket.settimeout(1.0)
                block = wire.socket.recv(8192)
                assert not block or b' 408 ' in block.split(b'\r\n', 1)[0]
            assert time.monotonic() - start < 1.5
    case('silent-and-trickle-deadline-isolation', deadlines)

    def slow_reader():
        with Wire() as stalled:
            stalled.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            stalled.send(request('/diagnostic-large'))
            for _ in range(12):
                exchange(request(), body=b'hello toksec\n')
    case('slow-response-reader-isolation', slow_reader)

    def recovery():
        for _ in range(80):
            with Wire() as abandoned:
                abandoned.send(b'GET /diagnostic-large HTTP/1.1\r\n')
        for _ in range(8):
            exchange(request('/data/65536'), body=bytes(range(256)) * 256)
    case('abandoned-connections-and-large-cache', recovery)
    print(json.dumps(dict(passed=all(item['passed'] for item in results), cases=results)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--custom', action='store_true')
    args = parser.parse_args()
    if args.inside:
        inside(args.custom)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    with sandbox.running(args.artifact, 1) as runtime:
        root = runtime['fixtures'] / 'www'
        for name, data in {'☃.txt': b'unicode\n', '%2e%2e': b'one pass\n',
                           'question?mark': b'question\n', 'hash#mark': b'hash\n'}.items():
            (root / name).write_bytes(data)
        (root / 'diagnostic-large').write_bytes(bytes(range(256)) * (64 * 1024))
        (root / 'linked-directory').symlink_to('directory', target_is_directory=True)
        (root / 'linked-missing').symlink_to('absent', target_is_directory=True)
        with socket.socket(socket.AF_UNIX) as unix_socket:
            unix_socket.bind(str(root / 'unix-socket'))
            process = subprocess.run(['nsenter', '--target', str(runtime['pid']), '--user', '--net',
                                      '--preserve-credentials', '--', sys.executable,
                                      str(Path(__file__).resolve()), '--inside'],
                                     text=True, capture_output=True, timeout=25)
        if process.returncode:
            raise RuntimeError(process.stderr)
        result = json.loads(process.stdout)
        result['source_sha256'] = hashlib.sha256((args.artifact / 'main.rs').read_bytes()).hexdigest()
        result['artifact'] = str(args.artifact.resolve())
        result['server_diagnostics'] = (runtime['fixtures'] / 'server.log').read_text()
    custom = '''# custom settings and whitespace are valid

 listen = 127.0.0.1:8089
 root = /fixtures/www/directory
max_connections=3
header_bytes=128
header_timeout_ms=90
idle_timeout_ms=93
write_timeout_ms=100
max_requests=7
pipeline_depth=2
'''
    with sandbox.running(args.artifact, 1, custom) as runtime:
        process = subprocess.run(['nsenter', '--target', str(runtime['pid']), '--user', '--net',
                                  '--preserve-credentials', '--', sys.executable,
                                  str(Path(__file__).resolve()), '--inside', '--custom'],
                                 text=True, capture_output=True, timeout=10)
        if process.returncode:
            raise RuntimeError(process.stderr)
        extra = json.loads(process.stdout)
        result['cases'].extend(extra['cases'])
        result['passed'] &= extra['passed']
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        sys.exit(2)


if __name__ == '__main__':
    main()
