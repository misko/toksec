import zlib
import os
import signal
import socket
import time
from pathlib import Path
from toksec.wire import Wire, payload, request
from toksec.check_types import registry

CASES, case = registry()

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
