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




@case('routing-interactions', 3, 'Queries survive directory redirects; aliases remain confined; ranges and conditionals apply after routing.')
def interactions(c):
    assert c.get('/directory?x=1', status=301).header('location') == '/directory/?x=1'
    c.get('/assets/%2e%2e/hello.txt', status=403)
    for path, host, body in [('/hello.txt', 'beta.test', b'beta toksec\n'), ('/assets/item.txt', 'alpha.test', b'asset\n'), ('/directory/', 'alpha.test', b'<p>index</p>\n')]:
        normal = c.get(path, host=host, body=body)
        tag = normal.header('etag')
        assert tag
        result = c.get(path, host=host, headers={'Range': 'bytes=1-999999'}, status=206, body=body[1:])
        assert result.header('content-range') == f'bytes 1-{len(body)-1}/{len(body)}'
        result = c.get(path, host=host, headers={'If-None-Match': tag, 'Range': 'bytes=999999-'}, status=304, body=b'')
        assert result.header('content-length') == '0' and result.header('etag') == tag


from toksec.stages import module as stage_module
OWN = CASES
CASES = stage_module(2, 'api').CASES + OWN
