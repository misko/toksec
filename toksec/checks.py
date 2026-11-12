import zlib
import json
import os
import signal
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from toksec.wire import Wire, payload, request


@dataclass(frozen=True)
class Case:
    id: str
    minimum: int
    description: str
    execute: object


CASES = []
EXTERNAL_CASES = [Case('configuration', 1, 'Invalid, duplicate, missing and unknown config values exit nonzero before serving.', None)]


def case(identity, minimum, description):
    def register(function):
        CASES.append(Case(identity, minimum, description, function))
        return function
    return register


class Context:
    def __init__(self, level, fixtures, server_pid, upstreams=None):
        self.level = level
        self.fixtures = Path(fixtures)
        self.pid = server_pid
        self.upstreams = upstreams
        self.original_config = (self.fixtures / 'server.conf').read_text()

    def exchange(self, raw=None, *, head=False, tls=False, server_name='alpha.test'):
        with Wire(8443 if tls else 8080, tls=tls, host=server_name) as wire:
            wire.send(raw or request())
            result = wire.read(head=head)
            if self.level == 1:
                assert result.header('connection', '').lower() == 'close'
                assert wire.stream.read(1) == b'', 'connection did not close'
            return result

    def get(self, path='/hello.txt', status=200, body=None, **kwargs):
        result = self.exchange(request(path, **kwargs), head=kwargs.get('method') == 'HEAD')
        assert result.status == status, f'{path}: expected {status}, got {result.status}'
        if body is not None:
            assert result.body == body, 'incorrect body bytes'
        return result

    def reload(self, changes=None, invalid=False):
        values = dict(line.split('=', 1) for line in self.original_config.splitlines() if line)
        values.update(changes or {})
        data = '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n'
        if invalid:
            data += 'unrecognized=true\n'
        (self.fixtures / 'server.conf').write_text(data)
        os.kill(self.pid, signal.SIGHUP)
        time.sleep(0.15)


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


@case('hosts', 3, 'Host routing is case-insensitive; absent, duplicate and unknown HTTP/1.1 hosts fail.')
def hosts(c):
    c.get(host='BETA.TEST:8080', body=b'beta toksec\n')
    for host in (None, 'unknown.test'):
        c.get(host=host, status=400)
    raw = request(headers={'Host': 'beta.test'})
    assert c.exchange(raw).status == 400


@case('routes-index-mime', 3, 'Exact redirects, prefix aliases, directory indexes and MIME types work.')
def routes(c):
    result = c.get('/old', status=302)
    assert result.header('location') == '/hello.txt'
    c.get('/assets/item.txt', body=b'asset\n')
    result = c.get('/directory', status=301)
    assert result.header('location') == '/directory/'
    result = c.get('/directory/', body=b'<p>index</p>\n')
    assert result.header('content-type', '').split(';')[0] == 'text/html'
    assert c.get().header('content-type', '').split(';')[0] == 'text/plain'


@case('etag', 3, 'Stable ETags and matching conditional requests return an empty 304.')
def etag(c):
    tag = c.get().header('etag')
    assert tag and tag.startswith('"') and tag.endswith('"')
    assert c.get().header('etag') == tag
    for match in (tag, '*'):
        c.get(headers={'If-None-Match': match}, status=304, body=b'')
    c.get(headers={'If-None-Match': '"different"'}, body=b'hello toksec\n')


@case('ranges', 3, 'Closed, open and suffix byte ranges plus HEAD, invalid and unsatisfiable ranges.')
def ranges(c):
    for value, expected, content_range in [('bytes=1-3', b'ell', 'bytes 1-3/13'),
                                          ('bytes=10-', b'ec\n', 'bytes 10-12/13'),
                                          ('bytes=-3', b'ec\n', 'bytes 10-12/13')]:
        result = c.get(headers={'Range': value}, status=206, body=expected)
        assert result.header('content-range') == content_range
    result = c.get(headers={'Range': 'bytes=99-'}, status=416)
    assert result.header('content-range') == 'bytes */13'
    c.get(headers={'Range': 'bytes=1-2,4-5'}, status=400)
    result = c.get(method='HEAD', headers={'Range': 'bytes=1-3'}, status=206, body=b'')
    assert result.header('content-length') == '3'


@case('proxy-get-and-post', 4, 'Proxy exact bytes and query; relay Content-Length and chunked POST bodies.')
def proxy(c):
    c.get('/proxy/data/4096', body=payload(4096))
    c.get('/proxy/echo?x=1', body=b'GET /echo?x=1\n')
    result = c.exchange(request('/proxy/echo', method='POST', headers={'Content-Length': '3'}, body=b'abc'))
    assert result.status == 200 and result.body == b'POST /echo\nabc'
    result = c.exchange(request('/proxy/echo', method='POST', headers={'Transfer-Encoding': 'chunked'}, body=b'3\r\nabc\r\n0\r\n\r\n'))
    assert result.status == 200 and result.body == b'POST /echo\nabc'
    c.get('/proxy/chunked', body=b'chunked response')


@case('proxy-framing-and-hops', 4, 'Reject ambiguous uploads; strip hop-by-hop headers in both directions.')
def proxy_headers(c):
    result = c.exchange(request('/proxy/echo', method='POST', headers={'Transfer-Encoding': 'chunked', 'Content-Length': '0'}, body=b'0\r\n\r\n'))
    assert result.status == 400
    result = c.exchange(request('/proxy/headers', headers={'Connection': 'close, X-Secret', 'X-Secret': 'remove'}))
    assert result.status == 200 and b'x-secret' not in result.body.lower()
    assert result.header('x-upstream-hop') is None
    c.get('/proxy/oversize', status=502)
    result = c.exchange(request('/proxy/echo', method='POST', headers={'Content-Length': '1048577'}))
    assert result.status == 413


@case('proxy-pool-and-errors', 4, 'Round robin, upstream reuse, malformed upstream rejection and timeout response.')
def proxy_pool(c):
    ids = [c.get('/proxy/id').body for _ in range(4)]
    assert ids[0] != ids[1] and ids[0] == ids[2] and ids[1] == ids[3]
    ports = [c.get('/proxy/connection').body for _ in range(4)]
    assert ports[0] == ports[2] and ports[1] == ports[3], 'upstream connections not reused'
    c.get('/proxy/bad-framing', status=502)
    c.get('/proxy/slow', status=504)


@case('proxy-no-post-retry', 4, 'An upstream disconnect after receiving POST must not replay the operation.')
def no_post_retry(c):
    before = int(c.get('/proxy/abort-count').body)
    result = c.exchange(request('/proxy/abort-post', method='POST', headers={'Content-Length': '3'}, body=b'abc'))
    assert result.status == 502
    assert int(c.get('/proxy/abort-count').body) == before + 1


@case('tls', 5, 'TLS >= 1.2 serves exact file bytes and Host routing with SNI.')
def tls(c):
    result = c.exchange(request(), tls=True)
    assert result.status == 200 and result.body == b'hello toksec\n'
    result = c.exchange(request(host='beta.test'), tls=True, server_name='beta.test')
    assert result.body == b'beta toksec\n'


@case('gzip', 5, 'Negotiated gzip has correct bytes and Vary; q=0 and ranges remain uncompressed.')
def compression(c):
    result = c.get('/text/4096.txt', headers={'Accept-Encoding': 'gzip'})
    assert result.header('content-encoding') == 'gzip'
    assert 'accept-encoding' in result.header('vary', '').lower()
    decoder = zlib.decompressobj(31)
    assert decoder.decompress(result.body, 4097) == payload(4096, True)
    assert decoder.eof and not decoder.unconsumed_tail
    head = c.get('/text/4096.txt', method='HEAD', headers={'Accept-Encoding': 'gzip'}, body=b'')
    assert head.header('content-length') == result.header('content-length')
    assert head.header('content-encoding') == 'gzip'
    result = c.get('/text/4096.txt', headers={'Accept-Encoding': 'gzip;q=0'}, body=payload(4096, True))
    assert result.header('content-encoding') is None
    result = c.get('/text/4096.txt', headers={'Accept-Encoding': 'gzip', 'Range': 'bytes=0-2'}, status=206, body=b'tok')
    assert result.header('content-encoding') is None


@case('cache', 5, 'Cache hit, expiry, host/query isolation, no-store and authorization bypass.')
def cache(c):
    path = '/proxy/counter?case=cache'
    first = c.get(path).body
    assert c.get(path).body == first
    assert c.get(path + '2').body != first
    assert c.get(path, host='beta.test').body != first
    assert c.exchange(request(path), tls=True).body != first
    time.sleep(1.2)
    assert c.get(path).body != first
    for extra, headers in (('&no_store=1', {}), ('&auth=1', {'Authorization': 'Bearer test'}),
                           ('&cookie=1', {}), ('&vary_star=1', {}), ('&private=1', {}), ('&vary_other=1', {})):
        a = c.get(path + extra, headers=headers).body
        assert c.get(path + extra, headers=headers).body != a
    variant = path + '&vary_encoding=1'
    plain = c.get(variant).body
    encoded = c.get(variant, headers={'Accept-Encoding': 'gzip'}).body
    assert encoded != plain
    assert c.get(variant).body == plain
    assert c.get(variant, headers={'Accept-Encoding': 'gzip'}).body == encoded
    c.get(path + '&head_first=1', method='HEAD', body=b'')
    assert c.get(path + '&head_first=1').body


@case('cache-byte-limit', 5, 'Cache eviction keeps retained response body bytes within the configured capacity.')
def cache_limit(c):
    try:
        c.reload({'cache_bytes': '16', 'cache_ttl_ms': '10000'})
        originals = {f'/proxy/counter?bounded={i}': c.get(f'/proxy/counter?bounded={i}').body for i in range(12)}
        assert sum(map(len, originals.values())) > 16
        retained_bytes = sum(len(body) for path, body in originals.items() if c.get(path).body == body)
        assert retained_bytes <= 16
    finally:
        c.reload()


@case('reload-and-rate-limit', 5, 'Valid reload changes roots atomically; invalid reload retains config; token bucket rejects excess.')
def reload_and_rate(c):
    try:
        c.reload({'root': '/www/beta'})
        c.get(body=b'beta toksec\n')
        c.reload({'root': '/www'}, invalid=True)
        c.get(body=b'beta toksec\n')
        c.reload({'rate_per_second': '1', 'rate_burst': '2'})
        responses = [c.exchange(request('/empty')) for _ in range(6)]
        statuses = [r.status for r in responses]
        assert statuses[:2] == [200, 200] and all(s == 429 for s in statuses[2:]), statuses
        assert all(int(r.header('retry-after', '0')) > 0 for r in responses[2:])
    finally:
        c.reload()


@case('graceful-stop', 5, 'SIGTERM finishes an in-flight response, closes listeners and exits within drain deadline.')
def drain(c):
    with Wire() as wire:
        wire.send(request('/large'))
        time.sleep(0.03)
        os.kill(c.pid, signal.SIGTERM)
        result = wire.read()
        assert result.status == 200 and result.body == payload(2 * 1024 * 1024)
    deadline = time.monotonic() + 2.7
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', 8080), 0.1):
                pass
        except OSError:
            try:
                status = Path(f'/proc/{c.pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
                if status == 'Z':
                    return
            except FileNotFoundError:
                return
        time.sleep(0.05)
    raise AssertionError('listener remained open after SIGTERM')


def run_checks(context):
    results = []
    for check in CASES:
        if check.minimum > context.level:
            continue
        started = time.monotonic()
        try:
            check.execute(context)
            results.append({'id': check.id, 'passed': True, 'seconds': time.monotonic() - started})
        except Exception as error:
            results.append({'id': check.id, 'passed': False, 'seconds': time.monotonic() - started,
                            'error': f'{type(error).__name__}: {error}'[:1000]})
    return {'cases': results, 'passed': all(r['passed'] for r in results)}
