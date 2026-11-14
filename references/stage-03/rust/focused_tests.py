"""Independent Stage 3 edge tests. Uses the unchanged sandbox and a compiled artifact."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from toksec.wire import Wire, request, payload


def driver():
    deadline = time.monotonic() + 2
    while True:
        try:
            with socket.create_connection(('127.0.0.1', 8080), .1):
                break
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(.01)
    cases = []
    def check(name, callback):
        started = time.monotonic()
        try:
            callback()
            cases.append(dict(id=name, passed=True, seconds=time.monotonic()-started))
        except Exception as e:
            cases.append(dict(id=name, passed=False, error=repr(e)))
    def exchange(path='/hello.txt', expected=200, body=None, method='GET', headers=None, host='gamma.test'):
        with Wire() as wire:
            wire.send(request(path, method=method, headers=headers, host=host))
            r = wire.read(head=method == 'HEAD')
            assert r.status == expected, (path, headers, r.status, expected)
            if body is not None:
                assert r.body == body, (path, r.body[:100], body[:100])
            assert wire.stream.read(1) == b''
            return r
    def hosts():
        exchange(body=b'hello toksec\n')
        exchange(host='DELTA.TEST:8080', body=b'beta toksec\n')
        for value in [None, '', 'alpha.test', 'gamma.test:', 'gamma.test:no', 'gamma.test:65536', 'gamma.test:1:2', 'gamma.test extra', '-gamma.test']:
            exchange(host=value, expected=400)
        with Wire() as w:
            w.send(b'GET /hello.txt HTTP/1.0\r\n\r\n')
            assert w.read().body == b'hello toksec\n'
    check('varying-host-configuration-and-invalid-hosts', hosts)
    def routes():
        assert exchange('/legacy',302).header('location') == '/hello.txt'
        exchange('/old',404)
        exchange('/static/item.txt',body=b'asset\n')
        exchange('/static/%2e%2e/hello.txt',403)
        exchange('/static/link',403)
        exchange('/linkdir/index.html',403)
        exchange('/static/pipe',403)
        exchange('/emptydir/',403)
        exchange('/directory%2f',body=b'<p>index</p>\n')
        assert exchange('/directory?x=%26&y=2',301).header('location') == '/directory/?x=%26&y=2'
        exchange('/%252e%252e',body=b'literal percent name\n')
        exchange('/caf%C3%A9.txt',body=b'utf8\n')
        exchange('/hello.txt?unused=%bad',body=b'hello toksec\n')
    check('route-confinement-utf8-and-one-pass-decoding', routes)
    def ranges():
        for value, code, body in [('bytes=0-999',206,b'hello toksec\n'),('bytes=-999',206,b'hello toksec\n'),('bytes=0-0',206,b'h'),('bytes=-0',416,b''),('bytes=12-1',416,b''),('bytes=999999999999999999999999-',416,b''),('bytes=',400,b''),('bytes=-',400,b''),('bytes=a-2',400,b''),('bytes=1-2-3',400,b''),('bytes=1-2,',400,b''),('items=1-2',400,b'')]:
            exchange(headers={'Range':value},expected=code,body=body)
        exchange('/empty',headers={'Range':'bytes=0-'},expected=416,body=b'')
        r=exchange(method='HEAD',headers={'Range':'bytes=-3'},expected=206,body=b'')
        assert r.header('content-length') == '3' and r.header('content-range') == 'bytes 10-12/13'
        exchange('/absent',method='HEAD',expected=404,body=b'')
    check('range-edge-cases-and-head-framing', ranges)
    def conditional():
        for path in ['/hello.txt','/static/item.txt','/directory/']:
            tag=exchange(path).header('etag')
            for condition in [tag,'*','"other", '+tag,'W/'+tag]:
                r=exchange(path,304,b'',headers={'If-None-Match':condition,'Range':'bytes=malformed'})
                assert r.header('etag') == tag and r.header('content-length') == '0'
    check('conditional-precedence-lists-and-weak-tags', conditional)
    def boundary():
        base=b'GET /hello.txt HTTP/1.1\r\nHost: gamma.test\r\nConnection: close\r\nX: '
        for size, expected in [(256,200),(257,431)]:
            with Wire() as w:
                w.send(base+b'a'*(size-len(base)-4)+b'\r\n\r\n')
                assert w.read().status == expected
        with Wire() as w:
            w.send(b'GET /hello.txt HTTP/1.1\r\nHost: gamma.test\r\nX: \xff\xfe\r\nConnection: close\r\n\r\n')
            assert w.read().body == b'hello toksec\n'
    check('varying-header-limit-and-opaque-values', boundary)
    def pipeline():
        with Wire() as w:
            w.send(request('/hello.txt',host='gamma.test',close=False)*3000)
            for i in range(3):
                r=w.read()
                assert r.body == b'hello toksec\n'
                assert r.header('connection') == ('close' if i == 2 else 'keep-alive')
            assert w.stream.read(1) == b'', 'reset or data after final response'
    check('max-requests-final-response-survives-excess-pipeline', pipeline)
    def halfclose():
        with Wire() as w:
            w.send(request('/large',host='gamma.test',close=False)+request('/hello.txt',host='gamma.test',close=False))
            w.socket.shutdown(socket.SHUT_WR)
            assert w.read().body == payload(2*1024*1024)
            assert w.read().body == b'hello toksec\n'
            assert w.stream.read(1) == b''
    check('halfclosed-peer-retains-complete-pipeline',halfclose)
    def deadline():
        with Wire(timeout=1) as w:
            start=time.monotonic()
            w.send(b'GET /hello.txt HTTP/1.1\r\nHost: gamma.test\r\nX: ')
            for _ in range(3):
                time.sleep(.09)
                try: w.send(b'a')
                except OSError: break
            assert w.socket.recv(4096) == b''
            assert time.monotonic()-start < .6
    check('varying-absolute-header-deadline',deadline)
    def stalled():
        with Wire() as w:
            w.socket.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024)
            w.send(request('/stall',host='gamma.test',close=False))
            start=time.monotonic()
            for _ in range(12): exchange(body=b'hello toksec\n')
            assert time.monotonic()-start < .5
            time.sleep(.4)
        exchange(body=b'hello toksec\n')
    check('stalled-output-fairness-and-recovery',stalled)
    print(json.dumps(dict(passed=all(c['passed'] for c in cases), cases=cases)))


def main():
    if '--driver' in sys.argv:
        driver()
        return
    from toksec import sandbox
    from toksec.specification import configuration
    artifact=Path(sys.argv[1]).resolve()
    output=Path(sys.argv[2]); output.mkdir(parents=True,exist_ok=False)
    values=configuration(3)
    values.update(default_host='gamma.test',host_root='delta.test:/www/beta',alias='/static/:/www/assets/',redirect='/legacy:/hello.txt',max_requests='3',pipeline_depth='1',header_bytes='256',header_timeout_ms='200',idle_timeout_ms='250',write_timeout_ms='150',max_connections='8')
    with sandbox.running(artifact,3,''.join(f'{k}={v}\n' for k,v in values.items())) as runtime:
        www=runtime['fixtures']/'www'
        (www/'%2e%2e').write_bytes(b'literal percent name\n')
        (www/'café.txt').write_bytes(b'utf8\n')
        (www/'emptydir').mkdir()
        (www/'linkdir').symlink_to('directory')
        (www/'assets/link').symlink_to('../hello.txt')
        os.mkfifo(www/'assets/pipe')
        command=['nsenter','--target',str(runtime['pid']),'--user','--net','--preserve-credentials','--',sys.executable,str(Path(__file__).resolve()),'--driver']
        process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
        (output/'stderr.txt').write_text(process.stderr)
        result=json.loads(process.stdout) if process.returncode == 0 else dict(passed=False,error=process.stderr)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)

if __name__ == '__main__': main()
