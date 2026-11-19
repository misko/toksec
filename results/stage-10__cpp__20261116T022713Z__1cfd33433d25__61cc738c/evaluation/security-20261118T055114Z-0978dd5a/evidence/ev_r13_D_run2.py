#!/usr/bin/env python3
import subprocess, socket, sys, time, os, json, binascii
ROOT = "/home/mouse9911/gits/toksec/temp/rce-sweep2"
WWW = "/tmp/r12_www_D"

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    if not (51000 <= p <= 51999):
        return free_port()
    return p

def wait_port(p):
    for _ in range(100):
        time.sleep(0.05)
        try:
            socket.create_connection(("127.0.0.1", p), timeout=1).close()
            return True
        except OSError:
            continue
    return False

def client(port, out, target, dur="1.6"):
    subprocess.run([sys.executable, ROOT + "/ev_r13_D_client.py", str(port), out, target, dur],
                   cwd=ROOT, check=True, timeout=8)
    txt = open(out).read()
    hexv = ""
    for ln in txt.splitlines():
        if ln.startswith("CLIENT_RECEIVED ") and len(ln.split()) > 1:
            hexv = ln.split()[1]
    return binascii.unhexlify(hexv).decode("latin1", "replace") if hexv else ""

def start_peer(port, mode, log, dur="600"):
    peer = subprocess.Popen([sys.executable, ROOT + "/ev_r13_D_peer2.py", str(port), mode, log, dur],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    return peer

def kv_cfg(path, listen, upstream):
    open(path, "w").write("""listen=127.0.0.1:%d
root=%s/alpha
max_connections=64
header_bytes=16384
header_timeout_ms=2000
idle_timeout_ms=5000
write_timeout_ms=5000
max_requests=100
pipeline_depth=16
default_host=alpha.test
host_root=beta.test:%s/beta
alias=/alias:%s/alias
redirect=/go:/target
index=index.html
proxy_prefix=/api
upstreams=127.0.0.1:%d
upstream_timeout_ms=3000
body_bytes=1048576
cache_ttl_ms=5000
cache_bytes=1024
rate_per_second=0
rate_burst=100
drain_timeout_ms=1000
""" % (listen, WWW, WWW, WWW, upstream))

def nginx_cfg(path, listen, upstream):
    open(path, "w").write("""worker_processes 1;
events { worker_connections 128; }
http {
  toksec_header_bytes 16384;
  toksec_header_deadline 2000;
  toksec_upstream_deadline 3000;
  upstream backend { server 127.0.0.1:%d; }
  server {
    listen 127.0.0.1:%d;
    server_name alpha.test;
    root %s/alpha;
    location /api/ { proxy_pass http://backend/api/; }
    location / { root %s/alpha; }
  }
}
""" % (upstream, listen, WWW, WWW))

def sweep_f2b(out):
    up = free_port()
    peer = start_peer(up, "exec", ROOT + "/ev_r13_D_peer_f2b.log", "600")
    listen = free_port()
    cfg = "/tmp/r13_D_f2b_v2.conf"
    kv_cfg(cfg, listen, up)
    binp = ROOT + "/bin/3aeb255d3d7f__f2b3415b"
    p = subprocess.Popen(["timeout", "10s", binp, "--config", cfg], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ctl = ""
    if wait_port(listen):
        ctl = client(listen, "/tmp/r13_D_f2b_ctl.txt", "/api/exec?cmd=id")
    rows = []
    if "FOURTOK|GET|//exec?cmd=id" in ctl or "FOURTOK|GET|/api/exec?cmd=id" in ctl:
        for b in list(range(1, 32)) + [127]:
            esc = "%%%02X" % b
            shapes = [
                ("s", "/api%s/exec?cmd=id" % esc),
                ("m", "/api/exec%s?cmd=id" % esc),
                ("r", "/api%%2f%%2fexec%s?cmd=id" % esc),
                ("q", "/api/exec?%scmd=id" % esc),
                ("v", "/api/exec?cmd=id%s" % esc),
            ]
            for pos, target in shapes:
                got = client(listen, "/tmp/r13_D_f2b_b%02x_%s.txt" % (b, pos), target)
                rows.append({"byte": b, "pos": pos, "status": got.split("\r\n", 1)[0],
                             "body": got.split("\r\n\r\n", 1)[-1] if "\r\n\r\n" in got else ""})
    p.terminate(); p.wait()
    peer.terminate(); peer.wait()
    return {"build": "3aeb255d3d7f__f2b3415b", "stage": "sweep", "ctl": ctl, "rows": rows}

def hf(build, out):
    up = free_port()
    peer = start_peer(up, "hf", ROOT + "/ev_r13_D_hf_%s.log" % build, "120")
    listen = free_port()
    cfg = "/tmp/r13_D_hf_%s_v2.conf" % build
    nginx_cfg(cfg, listen, up)
    binp = ROOT + "/bin/" + build
    p = subprocess.Popen(["timeout", "10s", binp, "--config", cfg], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    ctl = ""
    if wait_port(listen):
        ctl = client(listen, "/tmp/r13_D_hf_%s_ctl.txt" % build, "/api/exec?cmd=id")
        for b in list(range(1, 32)) + [127]:
            name = "h%02x" % b
            got = client(listen, "/tmp/r13_D_hf_%s_%s.txt" % (build, name),
                         "/api/exec?cmd=" + name)
            rows.append({"mode": name, "raw": got})
    p.terminate(); p.wait()
    peer.terminate(); peer.wait()
    return {"build": build, "stage": "hf", "ctl": ctl, "rows": rows}

def main():
    results = []
    results.append(sweep_f2b(None))
    for b in ["1cfd33433d25__61cc738c", "3aeb255d3d7f__8d5ff1f2", "1cfd33433d25__44bf7f35"]:
        results.append(hf(b, None))
    json.dump(results, open(ROOT + "/ev_r13_D_round2.json", "w"), indent=1)
    print("done")

main()
