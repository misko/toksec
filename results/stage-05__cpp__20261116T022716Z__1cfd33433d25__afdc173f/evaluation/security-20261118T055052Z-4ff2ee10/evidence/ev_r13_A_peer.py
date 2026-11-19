import socket, threading, sys, time, subprocess, json

LOG = open(sys.argv[1], "a", buffering=1)
PORT = int(sys.argv[2])
MODE = sys.argv[3] if len(sys.argv) > 3 else "authok"
TOKEN = sys.argv[4] if len(sys.argv) > 4 else "Bearer x"

def run(cmd):
    try:
        return subprocess.run(["sh", "-c", cmd], capture_output=True, timeout=5).stdout
    except Exception as exc:
        return str(exc).encode()

def handle(client):
    client.settimeout(1.5)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = client.recv(16384)
            if not chunk:
                break
            data += chunk
    except Exception:
        pass
    head, _, body = data.partition(b"\r\n\r\n")
    names = []
    auth_present = False
    for line in head.split(b"\r\n")[1:]:
        name, sep, _ = line.partition(b":")
        if sep:
            names.append(name.decode("latin1").lower())
            if name.lower() == b"authorization":
                auth_present = True
    toks = head.split(b"\r\n")[0].split(b" ")
    exec_out = None
    if len(toks) >= 2 and toks[-1].startswith(b"HTTP/"):
        for tok in toks[1:-1]:
            if tok.split(b"?", 1)[0].split(b"/")[-1] == b"exec":
                cmd = tok.split(b"?cmd=", 1)[1].split(b"&")[0] if b"?cmd=" in tok else b"id"
                exec_out = run(cmd.decode("latin1")).decode("latin1").strip()
                break
    seg = {
        "port": PORT, "raw": head.decode("latin1"), "hex": head.hex(),
        "reqline": head.split(b"\r\n")[0].decode("latin1"),
        "tokens": len(toks), "headers": names, "auth": auth_present,
        "bodyhex": body.hex(),
    }
    if exec_out is not None:
        seg["exec"] = exec_out
    LOG.write(json.dumps(seg) + "\n")
    status, body_out = 200, b"BODY-0123456789"
    if exec_out is not None:
        body_out = b"EXEC:" + exec_out.encode()
    if MODE == "authok" and not auth_present:
        status, body_out = 401, b"AUTH-REQUIRED"
    elif MODE == "authok" and auth_present:
        status, body_out = 200, body_out
    elif MODE == "authforbid" and auth_present:
        status, body_out = 403, b"AUTH-FORBIDDEN"
    if MODE != "authforbid" and b"expect: 100-continue" in b" ".join(head.split(b"\r\n")[1:]).lower():
        try:
            client.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
        except Exception:
            pass
    reason = b"OK" if status == 200 else (b"Unauthorized" if status == 401 else b"Forbidden")
    response = (b"HTTP/1.1 " + str(status).encode() + b" " + reason +
                b"\r\nContent-Length: " + str(len(body_out)).encode() +
                b"\r\nConnection: close\r\n\r\n" + body_out)
    try:
        client.sendall(response)
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", PORT))
server.listen(32)
server.settimeout(60)
start = time.time()
while time.time() - start < 60:
    try:
        conn, _ = server.accept()
    except Exception:
        break
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
server.close()
