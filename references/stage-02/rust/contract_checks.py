"""Independent contract probes for the Stage 2 reference; no harness changes."""
import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
root = out / 'root'
root.mkdir()
(root / 'hello').write_bytes(b'hello\x00\xff\r\n')
(root / '%2e%2e').write_bytes(b'one decode')
(root / 'empty').write_bytes(b'')
(root / 'large').write_bytes(bytes(range(256)) * 32768)
(root / 'dir').mkdir()
(root / 'dir' / 'item').write_bytes(b'nested')
(root / 'link').symlink_to('hello')
(root / 'dirlink').symlink_to('dir', target_is_directory=True)
os.mkfifo(root / 'fifo')
server = str(Path(sys.argv[2]).resolve())
results = []

class Response:
    def __init__(self, stream, head=False):
        self.status = int(stream.readline().split()[1])
        self.fields = {}
        while True:
            line = stream.readline()
            if line == b'\r\n':
                break
            if not line:
                raise AssertionError('truncated headers')
            key, value = line.split(b':', 1)
            self.fields[key.lower()] = value.strip()
        self.body = b'' if head else stream.read(int(self.fields[b'content-length']))
        assert len(self.body) == (0 if head else int(self.fields[b'content-length']))

class Running:
    def __init__(self, **changes):
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        self.port = probe.getsockname()[1]
        probe.close()
        cfg = dict(listen=f'127.0.0.1:{self.port}', root=str(root), max_connections='8', header_bytes='128', header_timeout_ms='120', idle_timeout_ms='150', write_timeout_ms='120', max_requests='7', pipeline_depth='1')
        cfg.update(changes)
        self.conf = out / f'config-{len(results)}.txt'
        self.conf.write_text('# test config\n\n' + '\n'.join(f'{k}={v}' for k,v in cfg.items()) + '\n')
        self.log = (out / f'server-{len(results)}.log').open('wb')
        self.proc = subprocess.Popen(['taskset','-c','3',server,'--config',str(self.conf)], stdout=self.log, stderr=self.log)
        deadline = time.monotonic()+2
        while True:
            try:
                with self.connect():
                    break
            except OSError:
                assert self.proc.poll() is None, 'server exited during startup'
                if time.monotonic()>deadline:
                    raise TimeoutError('startup timeout')
                time.sleep(.01)
    def connect(self):
        s = socket.create_connection(('127.0.0.1', self.port), timeout=2)
        return s
    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=2)
        self.log.close()
    def exchange(self, raw, head=False):
        with self.connect() as s:
            s.sendall(raw)
            with s.makefile('rb') as f:
                return Response(f, head)

def req(path=b'/hello', method=b'GET', close=False):
    return method+b' '+path+b' HTTP/1.1\r\n'+(b'Connection: close\r\n' if close else b'')+b'\r\n'

def case(name, fn):
    start=time.monotonic()
    try:
        fn()
        results.append(dict(id=name, passed=True, seconds=time.monotonic()-start))
    except Exception as exc:
        results.append(dict(id=name, passed=False, error=repr(exc), seconds=time.monotonic()-start))

def check_pipeline():
    p=Running()
    try:
        with p.connect() as s:
            s.sendall(req()*9)
            with s.makefile('rb') as f:
                for i in range(7):
                    r=Response(f)
                    assert r.status==200 and r.body==b'hello\x00\xff\r\n'
                    assert r.fields[b'connection']==(b'close' if i==6 else b'keep-alive')
                assert f.read(1)==b''
    finally:p.close()

def check_head_order():
    p=Running(max_requests='20')
    try:
        with p.connect() as s:
            s.sendall(req(b'/absent',b'HEAD')+req(b'/large',b'HEAD')+req(close=True))
            with s.makefile('rb') as f:
                r=Response(f,True);assert r.status==404 and r.fields[b'content-length']==b'0'
                r=Response(f,True);assert r.status==200 and r.fields[b'content-length']==str(8*1024*1024).encode()
                r=Response(f);assert r.body==b'hello\x00\xff\r\n'
                assert f.read(1)==b''
    finally:p.close()

def check_paths():
    p=Running(max_requests='20')
    try:
        for path,status,body in [(b'/%252e%252e',200,b'one decode'),(b'/dir/../hello',403,None),(b'/dirlink/item',403,None),(b'/link',403,None),(b'/fifo',403,None),(b'/hello/.',403,None),(b'/dir/item',200,b'nested'),(b'/./hello',200,b'hello\x00\xff\r\n'),(b'/hello?x=%zz',200,b'hello\x00\xff\r\n')]:
            r=p.exchange(req(path,close=True));assert r.status==status,(path,r.status)
            if body is not None:assert r.body==body
    finally:p.close()

def check_syntax():
    p=Running()
    try:
        bad=[b'GET /hello HTTP/1.1\rX: y\r\n\r\n',b'GET /hello HTTP/1.1\r\nX: a\n\r\n',b'GET /hello HTTP/1.1\r\nBad Name: v\r\n\r\n',b'G(ET /hello HTTP/1.1\r\n\r\n',b'GET /hello HTTP/1.1\r\ncontent-length: +0\r\n\r\n',b'GET /hello HTTP/1.1\r\ncontent-length: 0,0\r\n\r\n']
        for raw in bad:assert p.exchange(raw).status==400,raw
        assert p.exchange(req(method=b'CUSTOM',close=True)).status==405
        assert p.exchange(b'GET /hello HTTP/1.1\r\nX-Byte: \xff\x80\r\nConnection: close\r\n\r\n').status==200
    finally:p.close()

def check_header_limits():
    p=Running()
    try:
        base=b'GET /hello HTTP/1.1\r\nX: '
        for n,code in [(128,200),(129,431)]:
            raw=base+b'a'*(n-len(base)-4)+b'\r\n\r\n'
            r=p.exchange(raw);assert r.status==code,(n,r.status)
    finally:p.close()

def check_timeouts():
    p=Running()
    try:
        with p.connect() as s:
            s.sendall(b'GET /hello HTTP/1.1\r\nX: ')
            start=time.monotonic()
            for _ in range(3):
                time.sleep(.035);s.sendall(b'a')
            assert s.recv(1)==b''
            assert time.monotonic()-start<.30
        with p.connect() as s:
            s.sendall(req())
            f=s.makefile('rb');assert Response(f).status==200
            start=time.monotonic();assert f.read(1)==b''
            assert .09<time.monotonic()-start<.35
            f.close()
    finally:p.close()

def check_stalled_slot():
    p=Running(max_connections='1')
    try:
        time.sleep(.02)
        with socket.socket() as stalled:
            stalled.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024)
            stalled.settimeout(2);stalled.connect(('127.0.0.1',p.port));stalled.sendall(req(b'/large'))
            time.sleep(.45)
            assert p.exchange(req(close=True)).status==200
    finally:p.close()

def check_config():
    good=dict(listen='127.0.0.1:12345',root=str(root),max_connections='1',header_bytes='128',header_timeout_ms='120',idle_timeout_ms='150',write_timeout_ms='120',max_requests='1',pipeline_depth='1')
    variants=[]
    for k,v in [('listen','127.0.0.1:+12345'),('listen','127.0.0.1:65536'),('listen','127.0.0.1:0'),('root','relative'),('root',str(root/'hello')),('max_connections','-1'),('header_bytes','18446744073709551616'),('idle_timeout_ms','1x'),('pipeline_depth','0')]:
        cfg=good.copy();cfg[k]=v;variants.append('\n'.join(f'{k}={v}' for k,v in cfg.items())+'\n')
    variants.append('\n'.join(f'{k}={v}' for k,v in good.items())+'\nlisten=127.0.0.1:12345\n')
    for i,text in enumerate(variants):
        path=out/f'invalid-{i}.conf';path.write_text(text)
        completed=subprocess.run(['taskset','-c','3',server,'--config',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
        assert completed.returncode!=0,(i,text)

for name,fn in [('pipeline-depth-one-and-custom-max-requests',check_pipeline),('head-and-error-pipeline-framing',check_head_order),('one-pass-path-and-component-confinement',check_paths),('strict-syntax-and-byte-values',check_syntax),('configured-header-byte-boundary',check_header_limits),('configured-absolute-and-idle-deadlines',check_timeouts),('configured-stalled-writer-slot-release',check_stalled_slot),('malformed-configuration-values',check_config)]:
    case(name,fn)
result=dict(passed=all(r['passed'] for r in results),cases=results,
            binary_sha256=hashlib.sha256(Path(server).read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(Path(server).with_name('main.rs').read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
sys.exit(0 if result['passed'] else 1)
