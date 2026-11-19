import socket, threading, time, os, sys, subprocess
ROOT='/tmp/toksec-hunt'; BIN=sys.argv[1] if len(sys.argv)>1 else ROOT+'/s5ub'
CFG=sys.argv[2] if len(sys.argv)>2 else ROOT+'/cfg5single'
CP=18451; UP=18471
resp=[]; lock=threading.Lock(); stop=False

srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(('127.0.0.1',UP)); srv.listen(8); srv.settimeout(0.2)
def handle(c):
    buf=b''
    try:
        c.settimeout(3)
        while b'\r\n\r\n' not in buf:
            d=c.recv(4096)
            if not d: return
            buf+=d
        with lock: out=resp.pop(0) if resp else b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'
        c.sendall(out)
        time.sleep(0.2)
    except Exception: pass
    finally:
        try: c.close()
        except: pass
def loop():
    while not stop:
        try: c,_=srv.accept()
        except socket.timeout: continue
        except OSError: break
        threading.Thread(target=handle,args=(c,),daemon=True).start()
threading.Thread(target=loop,daemon=True).start()

env=dict(os.environ); env['ASAN_OPTIONS']='log_path=%s/p4asan:abort_on_error=1:detect_leaks=0'%ROOT
env['UBSAN_OPTIONS']='print_stacktrace=1'
p=subprocess.Popen([BIN,'--config',CFG],stdout=open(ROOT+'/p4.log','wb'),stderr=subprocess.STDOUT,env=env)
time.sleep(0.6)

def req(raw,wait=2.0):
    s=socket.create_connection(('127.0.0.1',CP),2); s.settimeout(wait); s.sendall(raw)
    buf=b''
    try:
        while True:
            d=s.recv(65536)
            if not d: break
            buf+=d
            if b'\r\n\r\n' in buf: break
    except socket.timeout: pass
    s.close(); return buf

cases=[
 ('HEAD 200 CL=2^63', b'HTTP/1.1 200 OK\r\nContent-Length: 9223372036854775808\r\n\r\n', b'HEAD /proxy/h1 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
 ('HEAD 200 CL=ULLMAX', b'HTTP/1.1 200 OK\r\nContent-Length: 18446744073709551615\r\n\r\n', b'HEAD /proxy/h2 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
 ('HEAD 304 CL=2^63', b'HTTP/1.1 304 Not Modified\r\nContent-Length: 9223372036854775808\r\n\r\n', b'HEAD /proxy/h3 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
 ('GET 304 CL=555', b'HTTP/1.1 304 Not Modified\r\nContent-Length: 555\r\n\r\n', b'GET /proxy/h4 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
 ('GET 204 CL=777', b'HTTP/1.1 204 No Content\r\nContent-Length: 777\r\n\r\n', b'GET /proxy/h5 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
 ('HEAD 200 CL=0', b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', b'HEAD /proxy/h6 HTTP/1.1\r\nHost: alpha.test\r\n\r\n'),
]
for name,rq,cl in cases:
    with lock: resp.append(rq)
    out=req(cl,3.0)
    print('%-20s => %r'%(name, out[:220]))

stop=True; p.terminate(); time.sleep(0.2)
try: p.kill()
except: pass
try: srv.close()
except: pass
log=open(ROOT+'/p4.log','rb').read()
print('--- log(%d) ---'%len(log)); print(log[:1200].decode('latin1','replace'))
