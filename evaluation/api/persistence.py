import socket
import time
from toksec.wire import Wire, payload, request
from toksec.check_types import registry

CASES, case = registry()

@case('head', 2, 'HEAD has GET headers and length with no body, including missing files.')
def head(c):
    with Wire() as wire:
        wire.send(request('/data/4096', method='HEAD', close=False))
        result = wire.read(head=True)
        assert result.status == 200 and result.header('content-length') == '4096'
        wire.send(request())
        assert wire.read().body == b'hello toksec\n'
    c.get('/absent', method='HEAD', status=404, body=b'')


@case('persistent-pipeline', 2, 'Persistent and pipelined responses retain order and exact framing.')
def persistent(c):
    with Wire() as wire:
        wire.send(request('/hello.txt', close=False) + request('/data/4096', close=False) + request('/empty'))
        for body in (b'hello toksec\n', payload(4096), b''):
            assert wire.read().body == body
        assert wire.stream.read(1) == b''
    with Wire() as wire:
        wire.send(request('/empty', close=False) * 15 + request('/hello.txt'))
        for _ in range(15):
            assert wire.read().body == b''
        assert wire.read().body == b'hello toksec\n'


@case('connection-semantics', 2, 'HTTP/1.0 defaults to close; mixed-case Connection tokens override HTTP/1.1 persistence.')
def connection_semantics(c):
    for raw in (b'GET /hello.txt HTTP/1.0\r\n\r\n', request(close=False, headers={'Connection': 'keep-alive, ClOsE'})):
        with Wire() as wire:
            wire.send(raw)
            result = wire.read()
            assert result.status == 200 and result.body == b'hello toksec\n'
            assert result.header('connection', '').lower() == 'close'
            assert wire.stream.read(1) == b''


@case('connection-limits', 2, 'Close after 100 requests; close idle persistent connections after two seconds.')
def connection_limits(c):
    with Wire() as wire:
        for i in range(100):
            wire.send(request('/empty', close=False))
            result = wire.read()
            assert result.status == 200
            assert result.header('connection', '').lower() == ('close' if i == 99 else 'keep-alive')
        assert wire.stream.read(1) == b''
    with Wire(timeout=3) as wire:
        wire.send(request('/empty', close=False))
        wire.read()
        start = time.monotonic()
        assert wire.stream.read(1) == b''
        assert time.monotonic() - start < 2.7


@case('slow-client-fairness', 2, 'A slow sender and a stalled large-file reader do not block ordinary requests.')
def fairness(c):
    with Wire() as sender, Wire() as reader:
        sender.send(b'GET /hello.txt HTTP/1.1\r\nX: ')
        reader.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        reader.send(request('/large'))
        start = time.monotonic()
        for _ in range(8):
            c.get(body=b'hello toksec\n')
        assert time.monotonic() - start < 0.8, 'ordinary clients stalled'


@case('byte-header-values', 2, 'Opaque header values need not be UTF-8.')
def byte_header_values(c):
    r=c.exchange(b'GET /hello.txt HTTP/1.1\r\nHost: alpha.test\r\nX-Note: \xff\r\nConnection: close\r\n\r\n')
    assert r.status == 200 and r.body == b'hello toksec\n'


from stages.common.api import CASES as COMMON_CASES

CASES = COMMON_CASES + CASES

CONFIGURED_CASES, configured = registry()
CONFIGURATIONS = {
    'connection-capacity': {'max_connections': '2', 'header_timeout_ms': '5000'},
    'write-deadline': {'max_connections': '1', 'write_timeout_ms': '250'},
    'pipeline-backpressure': {'pipeline_depth': '2'},
}


@configured('connection-capacity', 2, 'A small configured connection limit rejects excess clients and recovers after disconnects.')
def connection_capacity(c):
    time.sleep(0.1)
    with Wire() as first, Wire() as second:
        first.send(b'GET /hello.txt HTTP/1.1\r\n')
        second.send(b'GET /hello.txt HTTP/1.1\r\n')
        time.sleep(0.1)
        try:
            with socket.create_connection(('127.0.0.1', 8080), 1) as excess:
                excess.settimeout(1)
                excess.sendall(request())
                assert excess.recv(1) == b'', 'excess connection was served'
        except (ConnectionResetError, ConnectionRefusedError, BrokenPipeError):
            pass
    time.sleep(0.1)
    c.get(body=b'hello toksec\n')


@configured('write-deadline', 2, 'A blocked writer releases its connection slot after the configured write deadline.')
def write_deadline(c):
    time.sleep(0.1)
    with socket.socket() as stalled:
        stalled.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        stalled.settimeout(2)
        stalled.connect(('127.0.0.1', 8080))
        stalled.sendall(request('/stall'))
        time.sleep(1)
        c.get(body=b'hello toksec\n')


@configured('pipeline-backpressure', 2, 'A burst beyond pipeline_depth retains ordered responses and does not block another client.')
def pipeline_backpressure(c):
    with Wire() as wire:
        wire.send(request('/stall', close=False) + request('/data/4096', close=False) * 6 + request('/empty'))
        time.sleep(0.1)
        c.get(body=b'hello toksec\n')
        assert wire.read().body == payload(8 * 1024 * 1024)
        for _ in range(6):
            assert wire.read().body == payload(4096)
        assert wire.read().body == b''
        assert wire.stream.read(1) == b''
