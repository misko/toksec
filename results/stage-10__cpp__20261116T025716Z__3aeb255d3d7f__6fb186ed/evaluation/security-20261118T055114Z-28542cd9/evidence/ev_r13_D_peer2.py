#!/usr/bin/env python3
# Lane D peer v2: exec mode echoes FOURTOK; hf mode replays the byte-specific
# X-P header for h01..h1f/h7f, falling back to the control header otherwise.
import socket, threading, sys, time, binascii
MODE = sys.argv[2]
LOG = sys.argv[3]
DUR = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0
RAW = []
CTLHDR = b"HTTP/1.1 200 OK\r\nX-Ctl: k\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO"
PROBE = (b"HTTP/1.1 200 OK\r\n"
         b"X-A: va\r\nX-Test: vt\r\nServer: vs\r\nDate: vd\r\nContent-Type: text/plain\r\n"
         b"X-Powered-By: vp\r\nVia: vv\r\nWarning: vw\r\nX-Cache: vc\r\nAge: 7\r\n"
         b"ETag: ve\r\nLast-Modified: vl\r\nLocation: /loc\r\nSet-Cookie: sc\r\n"
         b"X-P: vp\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO")
def build(name):
    try:
        v = int(name[1:], 16)
    except ValueError:
        return CTLHDR
    if not (0x01 <= v <= 0x1F or v == 0x7F):
        return CTLHDR
    return (b"HTTP/1.1 200 OK\r\nX-P: " + bytes([v]) + b"v\r\nContent-Length: 5"
            b"\r\nConnection: close\r\n\r\nHELLO")
def handle(c, idx):
    try:
        c.settimeout(0.7)
        d = b""
        while b"\r\n\r\n" not in d:
            x = c.recv(8192)
            if not x:
                break
            d += x
        line = d.split(b"\r\n", 1)[0]
        toks = line.split()
        if MODE == "exec":
            if len(toks) == 3 and toks[1] == b"/exec":
                out = (b"HTTP/1.1 200 OK\r\nContent-Length: 5"
                       b"\r\nConnection: close\r\n\r\nHELLO")
            else:
                body = b"FOURTOK|" + b"|".join(toks) + b"|RHEX=" + binascii.hexlify(line)
                out = (b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
                       + b"\r\nConnection: close\r\n\r\n" + body)
        elif MODE == "probe":
            out = PROBE
        elif MODE == "hf":
            name = "ctl"
            if len(toks) >= 2 and toks[1].startswith(b"/api/exec?cmd="):
                name = toks[1][len(b"/api/exec?cmd="):].decode("latin1")
            out = CTLHDR if idx == 0 else build(name)
        else:
            body = b"TOKS" + str(len(toks)).encode() + b"|" + b"|".join(toks)
            out = (b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
                   + b"\r\nConnection: close\r\n\r\n" + body)
        c.sendall(out)
        RAW.append(d)
        with open(LOG, "a") as f:
            f.write("### x=%d mode=%s\nUPSTREAM_READ %s\nUPSTREAM_WROTE %s\n"
                    % (len(RAW) - 1, MODE, binascii.hexlify(d).decode(), binascii.hexlify(out).decode()))
        time.sleep(0.05)
    except Exception:
        pass
    finally:
        try:
            c.close()
        except Exception:
            pass
def main():
    port = int(sys.argv[1])
    open(LOG, "w").close()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(128)
    s.settimeout(0.1)
    t0 = time.time()
    while time.time() - t0 < DUR:
        try:
            c, _ = s.accept()
        except (socket.timeout, OSError):
            continue
        threading.Thread(target=handle, args=(c, len(RAW)), daemon=True).start()
    s.close()
main()
