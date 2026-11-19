import time
from toksec.wire import Wire, payload, request
from toksec.check_types import registry

CASES, case = registry()

@case('bootstrap', 1, 'A working server serves an ordinary file, empty file and a missing-file error.')
def bootstrap(c):
    c.get(body=b'hello toksec\n')
    c.get('/empty', body=b'')
    c.get('/absent', status=404)


@case('files', 1, 'Exact ordinary, empty, binary and 2 MiB files; missing file returns 404.')
def files(c):
    c.get(body=b'hello toksec\n')
    c.get('/empty', body=b'')
    c.get('/data/4096', body=payload(4096))
    c.get('/large', body=payload(2 * 1024 * 1024))
    c.get('/absent', status=404)


@case('query-and-decoding', 1, 'Query does not select a different file; strict one-pass percent decoding.')
def decoding(c):
    c.get('/hello.txt?ignored=yes', body=b'hello toksec\n')
    c.get('/space%20name.txt', body=b'space\n')
    for path in ('/%', '/%GG', '/%ff', '/%00', '/%5c', '/hello.txt#fragment', 'http://alpha.test/hello.txt'):
        c.get(path, status=400)


@case('confinement', 1, 'Traversal and symlinks are forbidden; nonregular objects and trailing file slash are not served.')
def confinement(c):
    for path in ('/../secret', '/%2e%2e/secret', '/escape', '/inside-link', '/pipe'):
        c.get(path, status=403)
    assert c.exchange(request('/hello.txt/')).status in (403, 404)
    if c.level < 3:
        c.get('/directory/', status=403)


@case('fragmentation', 1, 'A request split at each byte remains valid.')
def fragmentation(c):
    with Wire() as wire:
        for byte in request():
            wire.send(bytes([byte]))
        result = wire.read()
        assert result.status == 200 and result.body == b'hello toksec\n'


@case('syntax', 1, 'Malformed request/header/version, folded headers and unsupported methods have explicit errors.')
def syntax(c):
    requests = [b'GET / HTTP/2.0\r\n\r\n', b'GET  / HTTP/1.1\r\n\r\n',
                b'GET / HTTP/1.1\r\nBroken\r\n\r\n', b'GET / HTTP/1.1\r\n X: a\r\n\r\n',
                b'GET / HTTP/1.1\r\nX\x00: a\r\n\r\n', b'GET / HTTP/1.1\n\n']
    for raw in requests:
        assert c.exchange(raw).status == 400
    c.get(method='DELETE', status=405)


@case('request-framing', 1, 'Local request bodies, ambiguous lengths and transfer coding are rejected; decimal zero is valid.')
def framing(c):
    for fields in ('Content-Length: 1\r\n', 'Content-Length: -1\r\n',
                   'Content-Length: 0\r\nContent-Length: 0\r\n', 'Transfer-Encoding: chunked\r\n'):
        raw = b'GET /hello.txt HTTP/1.1\r\nHost: alpha.test\r\n' + fields.encode() + b'\r\n'
        assert c.exchange(raw).status == 400
    c.get(headers={'Content-Length': '000'}, body=b'hello toksec\n')


@case('header-limit', 1, 'Header section exactly 8192 bytes is accepted; 8193 bytes returns 431.')
def header_limit(c):
    base = b'GET /hello.txt HTTP/1.1\r\nHost: alpha.test\r\nX: '
    for length, expected in ((8192, 200), (8193, 431)):
        raw = base + b'a' * (length - len(base) - 4) + b'\r\n\r\n'
        assert c.exchange(raw).status == expected


@case('absolute-header-deadline', 1, 'Slow fragments cannot extend the one-second absolute header deadline.')
def header_deadline(c):
    with Wire(timeout=2) as wire:
        start = time.monotonic()
        wire.send(b'GET /hello.txt HTTP/1.1\r\nX: ')
        for _ in range(6):
            time.sleep(0.2)
            try:
                wire.send(b'a')
            except OSError:
                break
        wire.socket.settimeout(max(0.05, 1.65 - (time.monotonic() - start)))
        received = b''
        while True:
            block = wire.socket.recv(4096)
            if not block:
                break
            received += block
            assert len(received) <= 8192
        assert time.monotonic() - start < 1.7
        assert not received or b' 408 ' in received.split(b'\r\n', 1)[0]


@case('disconnect-recovery', 1, 'Incomplete and abandoned clients do not prevent later valid service.')
def recovery(c):
    with Wire() as wire:
        wire.send(b'GET /hello')
    c.get(body=b'hello toksec\n')


@case('headerless-request', 1, 'HTTP/1.0 accepts a GET without header fields.')
def headerless_request(c):
    r=c.exchange(b'GET /hello.txt HTTP/1.0\r\n\r\n')
    assert r.status == 200 and r.body == b'hello toksec\n'
