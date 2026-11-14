#!/usr/bin/env python3
"""Explicit scheduled socket correctness test; emits no performance claims."""
import argparse
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import selectors
import socket
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('supplemental', HERE / 'supplemental.py')
supplemental = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supplemental)
from toksec.wire import payload, request


def serve(connection, cpu, reply):
    os.sched_setaffinity(0, {cpu})
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(8192)
    listener.setblocking(False)
    connection.send(listener.getsockname()[1]); connection.close()
    selector = selectors.DefaultSelector()
    selector.register(listener, selectors.EVENT_READ)
    pending = {}
    while True:
        for key, events in selector.select():
            sock = key.fileobj
            if sock is listener:
                while True:
                    try: peer, _ = listener.accept()
                    except BlockingIOError: break
                    peer.setblocking(False)
                    pending[peer] = [bytearray(), 0]
                    selector.register(peer, selectors.EVENT_READ)
                continue
            try:
                state = pending[sock]
                if events & selectors.EVENT_READ:
                    raw = sock.recv(8192)
                    if not raw: raise ConnectionError('closed')
                    state[0].extend(raw)
                    if len(state[0]) > 65536: raise ConnectionError('oversize request')
                    if b'\r\n\r\n' not in state[0]: continue
                    selector.modify(sock, selectors.EVENT_WRITE)
                if events & selectors.EVENT_WRITE:
                    state[1] += sock.send(reply[state[1]:])
                    if state[1] == len(reply): raise ConnectionError('reply completed')
            except BlockingIOError:
                pass
            except (OSError, ConnectionError):
                selector.unregister(sock); pending.pop(sock); sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-cpu', type=int, required=True)
    parser.add_argument('--worker-cpu', type=int, required=True)
    parser.add_argument('--worker', type=Path, required=True, help='already compiled native_load binary')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.server_cpu == args.worker_cpu or not {args.server_cpu, args.worker_cpu} <= os.sched_getaffinity(0):
        parser.error('two distinct available scheduled CPUs required')
    body = payload(4096)
    normal = b'HTTP/1.1 200 OK\r\nContent-Length: 4096\r\nConnection: close\r\n\r\n' + body
    variants = {
        'correct_reconnect': (normal, None),
        'bad_status': (normal.replace(b'200 OK', b'503 NO', 1), 'status'),
        'duplicate_length': (normal.replace(b'Connection:', b'Content-Length: 4096\r\nConnection:', 1), 'content_length'),
        'corrupt_payload': (normal[:-1] + b'!', 'payload'),
        'truncated_payload': (normal[:-1], 'truncated'),
    }
    report = {'purpose': 'socket correctness only; deliberately faulty responses; not a performance measurement',
              'worker_binary_sha256': supplemental.digest(args.worker), 'cases': {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # This uses the same campaign lock as all other reference traffic.
    import fcntl
    lockpath = supplemental.ROOT / '.runs/references/validation.lock'
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, (reply, error) in variants.items():
            parent, child = multiprocessing.Pipe(duplex=False)
            fixture = multiprocessing.Process(target=serve, args=(child, args.server_cpu, reply))
            fixture.start(); child.close()
            try:
                if not parent.poll(3): raise RuntimeError('fault fixture not ready')
                port = parent.recv()
                with tempfile.TemporaryDirectory(prefix='toksec-native-fault-') as temporary:
                    raw = Path(temporary) / 'request.bin'; raw.write_bytes(request('/data/4096', close=False))
                    command = [str(args.worker.resolve()), '--size', '4096', '--clients', '64', '--persistent', '1',
                               '--cpu', str(args.worker_cpu), '--port', str(port), '--start-ns', str(time.monotonic_ns() + 500000000),
                               '--request', str(raw)]
                    process = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    if process.returncode: raise RuntimeError(process.stderr)
                    result = json.loads(process.stdout)
                assert result['attempts'] == result['successes'] + result['failures'], result
                assert sum(result['histogram']) == result['successes'], result
                assert result['clients_started'] == 64, result
                if error:
                    assert result['successes'] == 0 and result['completed_in_window'] == 0, result
                    assert result['failures'] > 0 and result['errors'].get(error, 0) > 0, result
                else:
                    assert result['successes'] > 0 and result['failures'] == 0 and result['warmup_failures'] == 0, result
                report['cases'][name] = {'passed': True, 'worker': result}
                supplemental.save(args.output, report)
                print(name + ': passed', flush=True)
            finally:
                parent.close(); fixture.terminate(); fixture.join(timeout=3)
                if fixture.is_alive(): fixture.kill(); fixture.join()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
