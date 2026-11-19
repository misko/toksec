#!/usr/bin/env python3
import socket, sys, binascii
port = int(sys.argv[1]); out = sys.argv[2]
target = sys.argv[3] if len(sys.argv) > 3 else "/api/exec?cmd=id"
dur = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
REQ = ("GET %s HTTP/1.1\r\nHost: alpha.test\r\nConnection: close\r\n\r\n" % target).encode("latin1")
res = b""; err = ""
try:
    c = socket.create_connection(("127.0.0.1", port), timeout=2)
    c.settimeout(dur)
    c.sendall(REQ)
    while True:
        x = c.recv(65536)
        if not x:
            break
        res += x
    c.close()
except Exception as e:
    err = repr(e)
    try:
        c.close()
    except Exception:
        pass
open(out, "w").write("REQUEST %s\nCLIENT_RECEIVED %s\nERR %s\nCLOSE_CLEAN %s\n"
                     % (binascii.hexlify(REQ).decode(), binascii.hexlify(res).decode(), err, "0" if err else "1"))
