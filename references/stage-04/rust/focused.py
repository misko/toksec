"""Supplemental contract checks. Executed by the coordinator through sandbox nsenter."""
import collections
import concurrent.futures
import struct
import json
import socket
import threading
import time

seen = collections.Counter()
connections = []
gate_lock = threading.Lock()
gate_active = 0
gate_peak = 0
gate_started = threading.Event()

def upstream(conn, identity):
    global gate_active, gate_peak
    connections.append(conn)
    try:
        f = conn.makefile('rb')
        while True:
            line = f.readline()
            if not line:
                return
            method, target, _ = line.rstrip(b'\r\n').split(b' ')
            headers = []
            while True:
                line = f.readline()
                if line == b'\r\n':
                    break
                k, v = line.rstrip(b'\r\n').split(b':', 1)
                headers.append((k.lower(), v.strip()))
            h = dict(headers)
            body = f.read(int(h.get(b'content-length', b'0')))
            seen[(identity, target)] += 1
            if target.startswith(b'/gate?'):
                with gate_lock:
                    gate_active += 1
                    gate_peak = max(gate_peak,gate_active)
                    gate_started.set()
                time.sleep(.25)
                with gate_lock:
                    gate_active -= 1
            if target == b'/failover' and identity == 0:
                return
            if target == b'/abort-post':
                return
            if target == b'/trickle':
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n')
                for _ in range(100):
                    conn.sendall(b'x')
                    time.sleep(.04)
                continue
            invalid = {
                b'/te-cl': b'Content-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
                b'/dup-te': b'Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
                b'/bad-chunk': b'Transfer-Encoding: chunked\r\n\r\n1;\r\nx\r\n0\r\n\r\n',
                b'/chunk-oversize': b'Transfer-Encoding: chunked\r\n\r\n100001\r\n',
                b'/bad-header': b'Bad Name: nope\r\nContent-Length: 0\r\n\r\n',
            }
            if target in invalid:
                conn.sendall(b'HTTP/1.1 200 OK\r\n' + invalid[target])
                return
            if target == b'/binary-chunk':
                payload = b'\x00\r\n\xffabc'
                conn.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n7; foo="a;b"\r\n'+payload+b'\r\n0\r\nX-Trailer: value\r\n\r\n')
                continue
            if target == b'/eof':
                conn.sendall(b'HTTP/1.1 200 OK\r\nConnection: close\r\nX-End: yes\r\n\r\neof-body')
                return
            if target == b'/huge-head':
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1048577\r\n\r\n')
                continue
            if target == b'/hops':
                payload = json.dumps({k.decode():v.decode('latin1') for k,v in headers}).encode()
                extra = b'Connection: keep-alive, X-Hop\r\nX-Hop: secret\r\nX-End: \xff\r\n'
            else:
                payload = target+b'\n'+body
                extra = b''
            code = b'207 Multi-Status' if target == b'/status' else b'200 OK'
            conn.sendall(b'HTTP/1.1 '+code+b'\r\nContent-Length: '+str(len(payload)).encode()+b'\r\n'+extra+b'\r\n'+(payload if method != b'HEAD' else b''))
    except (OSError, ValueError):
        pass
    finally:
        conn.close()

def serve(identity):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 8081+identity))
    listener.listen(512)
    while True:
        conn, _ = listener.accept()
        threading.Thread(target=upstream, args=(conn,identity), daemon=True).start()

for i in range(2):
    threading.Thread(target=serve, args=(i,), daemon=True).start()
time.sleep(.05)

def req(path='/hello.txt', method='GET', headers=(), body=b'', close=True):
    return (f'{method} {path} HTTP/1.1\r\nHost: alpha.test\r\n'.encode()+b''.join(k.encode()+b': '+v+b'\r\n' for k,v in headers)+(b'Connection: close\r\n' if close else b'')+b'\r\n'+body)

def read(f, head=False):
    line=f.readline()
    assert line, 'missing response'
    status=int(line.split()[1]); headers=[]
    while True:
        line=f.readline()
        if line == b'\r\n': break
        assert line, 'missing header terminator'
        k,v=line.rstrip(b'\r\n').split(b':',1);headers.append((k.lower(),v.strip()))
    h=dict(headers); length=int(h[b'content-length'])
    body=b'' if head else f.read(length)
    assert head or len(body)==length
    return status,h,body

def exchange(raw, head=False, halfclose=False):
    with socket.create_connection(('127.0.0.1',8080),2) as s:
        s.settimeout(3);s.sendall(raw)
        if halfclose:s.shutdown(socket.SHUT_WR)
        f=s.makefile('rb');result=read(f,head)
        if b'Connection: close' in raw: assert f.read(1)==b''
        return result

results=[]
def check(name, fn):
    start=time.monotonic()
    try:
        fn();results.append(dict(name=name,passed=True,seconds=time.monotonic()-start))
    except Exception as exc:
        results.append(dict(name=name,passed=False,error=repr(exc),seconds=time.monotonic()-start))

def failover():
    assert exchange(req('/proxy/failover'))[2] == b'/failover\n'
    assert seen[(0,b'/failover')]==seen[(1,b'/failover')]==1
check('GET transport retry on next upstream',failover)

def binary_upload():
    body=b'\x00\n\r\n\xff123'
    chunk=f'{len(body):x}; foo="a;b"\r\n'.encode()+body+b'\r\n0\r\nX-Trailer: opaque\r\n\r\n'
    assert exchange(req('/proxy/echo', 'POST', [('Transfer-Encoding',b'chunked')], chunk))[2]==b'/echo\n'+body
check('binary chunked upload with quoted extension and trailer',binary_upload)
check('binary chunked upstream response',lambda: (_ for _ in ()).throw(AssertionError()) if exchange(req('/proxy/binary-chunk'))[2]!=b'\x00\r\n\xffabc' else None)

def framing():
    for suffix in ('te-cl','dup-te','bad-chunk','chunk-oversize','bad-header'):
        assert exchange(req('/proxy/'+suffix))[0]==502,suffix
    for body in (b'1;\r\nx\r\n0\r\n\r\n',b'1;x=\r\nx\r\n0\r\n\r\n',b'1;x="unterminated\r\nx\r\n0\r\n\r\n'):
        assert exchange(req('/proxy/echo','POST',[('Transfer-Encoding',b'chunked')],body))[0]==400
check('malformed upstream and request chunk extensions',framing)

def slow_upload():
    with socket.create_connection(('127.0.0.1',8080),2) as s:
        s.settimeout(3)
        s.sendall(req('/proxy/slow-upload','POST',[('Content-Length',b'3')]))
        for byte in b'abc':
            time.sleep(.45)
            s.sendall(bytes([byte]))
        assert read(s.makefile('rb'))[2]==b'/slow-upload\nabc'
check('active uploads may outlast header deadline',slow_upload)

def no_post_retry():
    assert exchange(req('/proxy/abort-post','POST',[('Content-Length',b'3')],b'abc'))[0]==502
    assert seen[(0,b'/abort-post')]+seen[(1,b'/abort-post')]==1
check('POST failure is never replayed',no_post_retry)

def head_pipeline():
    with socket.create_connection(('127.0.0.1',8080),2) as s:
        s.settimeout(3);s.sendall(req('/proxy/head', 'HEAD', close=False)+req('/proxy/echo'))
        f=s.makefile('rb');a=read(f,True);b=read(f)
        assert a[0]==200 and a[1][b'content-length']==b'6'
        assert b[0]==200 and b[2]==b'/echo\n';assert f.read(1)==b''
    assert exchange(req('/proxy/huge-head','HEAD'),head=True)[1][b'content-length']==b'1048577'
check('proxy HEAD representation and pipeline framing',head_pipeline)

def hops():
    st,h,b=exchange(req('/proxy/hops',headers=[('Connection',b'keep-alive, X-Secret'),('X-Secret',b'remove'),('X-End',b'forward')]))
    assert st==200 and b'x-secret' not in b.lower() and b'x-hop' not in h and h[b'x-end']==b'\xff'
    assert json.loads(b)['x-end']=='forward'
check('hop removal and opaque end-to-end response header',hops)

def misc_proxy():
    assert exchange(req('/proxy/eof'))[2]==b'eof-body'
    assert exchange(req('/proxy/status'))[0]==207
    assert exchange(req('/proxy/a%20b?x=%2f'))[2]==b'/a%20b?x=%2f\n'
check('EOF response, forwarded status and escaped target',misc_proxy)

def deadline():
    start=time.monotonic();assert exchange(req('/proxy/trickle'))[0]==504
    assert time.monotonic()-start<1.3
check('absolute upstream completion deadline despite progress',deadline)

def halfclose():
    assert exchange(req(close=False),halfclose=True)[2]==b'hello toksec\n'
    assert exchange(req('/proxy/echo',close=False),halfclose=True)[2]==b'/echo\n'
check('local and proxy half-closed request stream',halfclose)

def max_requests():
    with socket.create_connection(('127.0.0.1',8080),2) as s:
        s.settimeout(3);s.sendall(req('/empty',close=False)*300)
        f=s.makefile('rb')
        for i in range(100):
            st,h,b=read(f);assert st==200 and not b
            assert h[b'connection']==(b'close' if i==99 else b'keep-alive')
        assert f.read(1)==b''
check('final max_requests response and EOF with unread pipeline',max_requests)
def queued_proxy_burst():
    def one(i):
        path=f'/proxy/gate?i={i}'
        with socket.create_connection(('127.0.0.1',8080),3) as s:
            s.settimeout(5)
            s.sendall(req(path,close=i%4!=0))
            if i%4==0:s.shutdown(socket.SHUT_WR)
            result=read(s.makefile('rb'))
            assert result[0]==200 and result[2]==f'/gate?i={i}\n'.encode()
    with concurrent.futures.ThreadPoolExecutor(max_workers=192) as pool:
        futures=[pool.submit(one,i) for i in range(192)]
        assert gate_started.wait(3)
        assert exchange(req())[2]==b'hello toksec\n'
        # Resets while the upstream limit is occupied must release slots and
        # must not attach stale queue entries to a later reused descriptor.
        for i in range(32):
            with socket.create_connection(('127.0.0.1',8080),3) as s:
                s.sendall(req(f'/proxy/gate?cancel={i}'))
                s.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
        for f in futures:f.result()
    assert gate_peak<=128,(gate_peak,'unbounded simultaneous exchanges')
    assert exchange(req('/proxy/after-queue'))[2]==b'/after-queue\n'
check('queued proxy burst preserves bytes, half closes and reset recovery',queued_proxy_burst)

print(json.dumps(dict(passed=all(r['passed'] for r in results),checks=results),indent=2))
