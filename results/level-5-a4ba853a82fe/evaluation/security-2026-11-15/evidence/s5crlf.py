import socket, threading, time, os, sys, subprocess
ROOT='/tmp/toksec-hunt'; BIN=sys.argv[1] if len(sys.argv)>1 else ROOT+'/s5ub'
CFG=sys.argv[2] if len(sys.argv)>2 else ROOT+'/cfg5single'
CP=18451; UP=18471
raw=[]; lock=threading.Lock(); stop=False

srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(('127.0.0.1',UP)); srv.listen(8); srv.settimeout(0.2)
def handle(c):
    buf=b''
    try:
        c.settimeout(2)
        while b'\r\n\r\n' not in buf:
            d=c.recv(65536)
            if not d: return
            buf+=d
        time.sleep(0.05)
        try:
            while True:
                d=c.recv(65536)
                if not d: break
                buf+=d
                if len(buf)>8192: break
        except socket.timeout: pass
        with lock: raw.append(buf)
        c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
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

env=dict(os.environ); env['ASAN_OPTIONS']='log_path=%s/p5asan:abort_on_error=1:detect_leaks=0'%ROOT
env['UBSAN_OPTIONS']='print_stacktrace=1'
p=subprocess.Popen([BIN,'--config',CFG],stdout=open(ROOT+'/p5.log','wb'),stderr=subprocess.STDOUT,env=env)
time.sleep(0.6)

def req(rawreq,wait=1.5):
    s=socket.create_connection(('127.0.0.1',CP),2); s.settimeout(wait); s.sendall(rawreq)
    buf=b''
    try:
        while True:
            d=s.recv(65536)
            if not d: break
            buf+=d
            if b'\r\n\r\n' in buf: break
    except socket.timeout: pass
    s.close(); return buf

tests=[
 b'GET /%70roxy/x%0D%0AX-Injected:%20yes HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
 b'GET /%70roxy/x%20y HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
 b'GET /%70roxy/x%0D%0A%0D%0AGET%20/smuggled%20HTTP/1.1%0D%0AHost:%20alpha.test HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
 b'GET /proxy/x%0D%0AX-Raw:%20yes HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
 b'GET /%70roxy/%2e%2e/x HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
 b'GET /%70roxy/x%09y HTTP/1.1\r\nHost: alpha.test\r\n\r\n',
]
for t in tests:
    before=len(raw); out=req(t); time.sleep(0.35)
    with lock: got=raw[before:]
    print('CLIENT :', t.split(b' HTTP')[0])
    print('  reply:', out.split(b'\r\n')[0])
    for r in got: print('  UPSTREAM SAW: %r'%r)
    print()
stop=True; p.terminate(); time.sleep(0.2)
try: p.kill()
except: pass
try: srv.close()
except: pass
log=open(ROOT+'/p5.log','rb').read()
print('--- log(%d) ---'%len(log)); print(log[:1200].decode('latin1','replace'))
