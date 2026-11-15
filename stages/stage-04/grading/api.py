import zlib
import os
import signal
import socket
import time
from pathlib import Path
from toksec.wire import Wire, payload, request
from toksec.check_types import registry

CASES, case = registry()

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




@case('proxy-fragmented-upload', 4, 'Fragmented chunk bodies and bounded trailers decode correctly; recovery follows rejected framing.')
def fragmented_upload(c):
    with Wire() as wire:
        raw = request('/proxy/echo', method='POST', headers={'Transfer-Encoding': 'chunked'}, body=b'2\r\nab\r\n1\r\nc\r\n0\r\nX-Note: value\r\n\r\n')
        for byte in raw:
            wire.send(bytes([byte]))
        result = wire.read()
        assert result.status == 200 and result.body == b'POST /echo\nabc'
    for body in (b'Z\r\n', b'1\r\naXX'):
        result = c.exchange(request('/proxy/echo', method='POST', headers={'Transfer-Encoding': 'chunked'}, body=body))
        assert result.status == 400
    c.get('/proxy/data/4096', body=payload(4096))


from toksec.stages import module as stage_module
OWN = CASES
CASES = stage_module(3, 'api').CASES + OWN
