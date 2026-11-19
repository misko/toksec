#!/usr/bin/env python3
# Lane D peer: echoes the upstream request line verbatim and returns its token count;
# mode hf replays a fixed response header block. Logs raw bytes in hex.
import socket, threading, sys, time, binascii, json
MODE = sys.argv[2]
LOG = sys.argv[3]
DUR = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0
RAW = []
HDRCTL = b"HTTP/1.1 200 OK\r\nX-Ctl: k\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO"
HF = {
    "ctl":       b"HTTP/1.1 200 OK\r\nX-Ctl: k\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h01":       b"HTTP/1.1 200 OK\r\nX-P: \x01v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h02":       b"HTTP/1.1 200 OK\r\nX-P: \x02v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h03":       b"HTTP/1.1 200 OK\r\nX-P: \x03v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h04":       b"HTTP/1.1 200 OK\r\nX-P: \x04v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h05":       b"HTTP/1.1 200 OK\r\nX-P: \x05v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h06":       b"HTTP/1.1 200 OK\r\nX-P: \x06v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h07":       b"HTTP/1.1 200 OK\r\nX-P: \x07v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h08":       b"HTTP/1.1 200 OK\r\nX-P: \x08v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h09":       b"HTTP/1.1 200 OK\r\nX-P: \x09v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0a":       b"HTTP/1.1 200 OK\r\nX-P: \x0av\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0b":       b"HTTP/1.1 200 OK\r\nX-P: \x0bv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0c":       b"HTTP/1.1 200 OK\r\nX-P: \x0cv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0d":       b"HTTP/1.1 200 OK\r\nX-P: \x0dv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0e":       b"HTTP/1.1 200 OK\r\nX-P: \x0ev\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h0f":       b"HTTP/1.1 200 OK\r\nX-P: \x0fv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h10":       b"HTTP/1.1 200 OK\r\nX-P: \x10v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h11":       b"HTTP/1.1 200 OK\r\nX-P: \x11v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h12":       b"HTTP/1.1 200 OK\r\nX-P: \x12v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h13":       b"HTTP/1.1 200 OK\r\nX-P: \x13v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h14":       b"HTTP/1.1 200 OK\r\nX-P: \x14v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h15":       b"HTTP/1.1 200 OK\r\nX-P: \x15v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h16":       b"HTTP/1.1 200 OK\r\nX-P: \x16v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h17":       b"HTTP/1.1 200 OK\r\nX-P: \x17v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h18":       b"HTTP/1.1 200 OK\r\nX-P: \x18v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h19":       b"HTTP/1.1 200 OK\r\nX-P: \x19v\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1a":       b"HTTP/1.1 200 OK\r\nX-P: \x1av\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1b":       b"HTTP/1.1 200 OK\r\nX-P: \x1bv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1c":       b"HTTP/1.1 200 OK\r\nX-P: \x1cv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1d":       b"HTTP/1.1 200 OK\r\nX-P: \x1dv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1e":       b"HTTP/1.1 200 OK\r\nX-P: \x1ev\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h1f":       b"HTTP/1.1 200 OK\r\nX-P: \x1fv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
    "h7f":       b"HTTP/1.1 200 OK\r\nX-P: \x7fv\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO",
}
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
        if MODE == "hf" or MODE == "hdrctl":
            name = "ctl"
            if len(toks) >= 2 and toks[1].startswith(b"/api/exec?cmd="):
                name = toks[1][len(b"/api/exec?cmd="):].decode("latin1")
            out = HDRCTL if (MODE == "hdrctl" or idx == 0) else HF.get(name, HF["ctl"])
        else:
            out = b"HTTP/1.1 200 OK\r\nContent-Length: "
        if MODE == "exec":
            out = b"HTTP/1.1 200 OK\r\nContent-Length: "
            if len(toks) == 3 and toks[1] == b"/exec":
                out += b"5\r\nConnection: close\r\n\r\nHELLO"
            else:
                body = b"FOURTOK|" + b"|".join(toks) + b"|RHEX=" + binascii.hexlify(line)
                out = (b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
                       + b"\r\nConnection: close\r\n\r\n" + body)
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
    n = 0
    while time.time() - t0 < DUR:
        try:
            c, _ = s.accept()
        except (socket.timeout, OSError):
            continue
        threading.Thread(target=handle, args=(c, n), daemon=True).start()
        n += 1
    s.close()
main()
