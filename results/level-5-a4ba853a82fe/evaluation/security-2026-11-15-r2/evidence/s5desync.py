import socket, threading, time, os, sys, subprocess, struct
ROOT='/tmp/toksec-hunt'; BIN=sys.argv[1] if len(sys.argv)>1 else ROOT+'/s5ub'
CFG=sys.argv[2] if len(sys.argv)>2 else ROOT+'/cfg5single'
CP=18451; UP=18471
log=[]; lock=threading.Lock(); ready=threading.Event()

srv_sock=socket.socket(); srv_sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv_sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,2048)   # tiny so proxy send hits EAGAIN
srv_sock.bind(('127.0.0.1',UP)); srv_sock.listen(8); srv_sock.settimeout(0.2)
stop=False

def handle(c):
    buf=b''
    try:
        c.settimeout(6)
        while b'\r\n\r\n' not in buf:
            d=c.recv(4096)
            if not d: return
            buf+=d
        e=buf.index(b'\r\n\r\n'); head=buf[:e]; rest=buf[e+4:]
        with lock: log.append(('HEAD', head.decode('latin1')))
        # respond IMMEDIATELY, before consuming the request body
        c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
        time.sleep(0.5)
        cl=0
        for ln in head.split(b'\r\n')[1:]:
            if ln.lower().startswith(b'content-length:'): cl=int(ln.split(b':',1)[1])
        got=len(rest); data=rest
        deadline=time.time()+4
        while got<cl and time.time()<deadline:
            d=c.recv(65536)
            if not d: break
            data+=d; got+=len(d)
        with lock:
            log.append(('BODYLEN', '%d of %d'%(got,cl)))
            tail=data[cl:] if got>cl else b''
            log.append(('TAIL', tail[:400].decode('latin1','replace')))
        # keep reading whatever else arrives
        extra=b''
        deadline=time.time()+1.5
        while time.time()<deadline:
            try:
                d=c.recv(65536)
            except socket.timeout: break
            if not d: break
            extra+=d
        with lock: log.append(('EXTRA', extra[:400].decode('latin1','replace')))
    except Exception as ex:
        with lock: log.append(('ERR', repr(ex)))
    finally:
        try: c.close()
        except: pass

def loop():
    while not stop:
        try: c,_=srv_sock.accept()
        except socket.timeout: continue
        except OSError: break
        threading.Thread(target=handle,args=(c,),daemon=True).start()
threading.Thread(target=loop,daemon=True).start()

env=dict(os.environ); env['ASAN_OPTIONS']='log_path=%s/p3asan:abort_on_error=1:detect_leaks=0'%ROOT
env['UBSAN_OPTIONS']='print_stacktrace=1'
p=subprocess.Popen([BIN,'--config',CFG],stdout=open(ROOT+'/p3.log','wb'),stderr=subprocess.STDOUT,env=env)
time.sleep(0.6)

def request(raw, wait=4.0):
    s=socket.create_connection(('127.0.0.1',CP),2); s.settimeout(wait); s.sendall(raw)
    buf=b''
    try:
        while True:
            d=s.recv(65536)
            if not d: break
            buf+=d
            if b'\r\n\r\n' in buf:
                h,b=buf.split(b'\r\n\r\n',1); cl=0
                for ln in h.split(b'\r\n')[1:]:
                    if ln.lower().startswith(b'content-length:'): cl=int(ln.split(b':',1)[1])
                if len(b)>=cl: break
    except socket.timeout: pass
    s.close(); return buf

# 1) big POST, upstream answers before the body is sent
body=b'A'*1000000
raw=(b'POST /proxy/p1 HTTP/1.1\r\nHost: alpha.test\r\nContent-Length: %d\r\n\r\n'%len(body))+body
print('resp1:', request(raw, 6.0)[:60])
time.sleep(1.0)
with lock:
    print('--- upstream view ---')
    for k,v in log: print(k, '::', v[:200])
    log.clear()

# 2) follow-up request that will reuse the pooled upstream fd
print('resp2:', request(b'GET /proxy/p2 HTTP/1.1\r\nHost: alpha.test\r\n\r\n', 4.0)[:80])
time.sleep(2.0)
with lock:
    print('--- upstream view (2) ---')
    for k,v in log: print(k, '::', v[:300])

stop=True; p.terminate(); time.sleep(0.2)
try: p.kill()
except: pass
try: srv_sock.close()
except: pass
out=open(ROOT+'/p3.log','rb').read()
print('--- server log (%d) ---'%len(out)); print(out[:1500].decode('latin1','replace'))
