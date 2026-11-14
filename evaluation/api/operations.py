import zlib
import os
import signal
import socket
import time
from pathlib import Path
from toksec.wire import Wire, payload, request
from toksec.check_types import registry

CASES, case = registry()

@case('cache', 5, 'Cache hit, expiry, host/query isolation, no-store and authorization bypass.')
def cache(c):
    path = '/proxy/counter?case=cache'
    first = c.get(path).body
    assert c.get(path).body == first
    assert c.get(path + '2').body != first
    assert c.get(path, host='beta.test').body != first
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


@case('cache-byte-limit', 5, 'Black-box eviction probes are consistent with the configured cached-body capacity; not proof of internal accounting.')
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
        wire.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        wire.send(request('/stall'))
        assert wire.socket.recv(1, socket.MSG_PEEK), 'response did not start'
        os.kill(c.pid, signal.SIGTERM)
        result = wire.read()
        assert result.status == 200 and result.body == payload(8 * 1024 * 1024)
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
