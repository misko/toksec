import socket, sys, time, json, os

LISTEN = int(sys.argv[1]); LOGFILE = sys.argv[2]; MODE = sys.argv[3]; TAG = sys.argv[4]
start = open(LOGFILE).read().count("\n") if os.path.exists(LOGFILE) else 0

def send(payload, wait=2.6):
    sock = socket.create_connection(("127.0.0.1", LISTEN), timeout=5)
    sock.sendall(payload)
    sock.settimeout(wait)
    data = b""; deadline = time.time() + wait
    while time.time() < deadline:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        except Exception:
            break
        if not chunk:
            break
        data += chunk
    time.sleep(0.3); sock.close(); return data

def show(label, payload):
    print(f"== {TAG} {label}: {len(payload)} bytes")
    print("  CLIENT_REQUEST_HEX", payload.hex())
    response = send(payload)
    print("  CLIENT_HEX", response.hex())
    print("  CLIENT_STATUS", response.split(b"\r\n")[0].decode("latin1") if response else "NOSP")
    time.sleep(1.0)

AUTH = b"Authorization: Bearer x\r\n"
BODY = b"GET /exec?cmd=id HTTP/1.1\r\nHost: x\r\n\r\n"
EXPECT = b"Expect: 100-continue\r\n"

if MODE == "plain":
    show("plain control", b"GET /api/hello.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n\r\n")
elif MODE == "auth_plain":
    show("auth control keep-alive", b"GET /api/f.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + AUTH + b"\r\n")
    show("auth payload Connection: authorization", b"GET /api/f.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: authorization\r\n" + AUTH + b"\r\n")
elif MODE == "auth_exec":
    show("auth exec control keep-alive", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + AUTH + b"Content-Length: 35\r\n\r\n" + BODY)
    show("auth exec payload Connection: authorization", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: authorization\r\n" + AUTH + b"Content-Length: 35\r\n\r\n" + BODY)
elif MODE == "auth_forbid":
    show("forbid control without header", b"GET /api/hello.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n\r\n")
    show("forbid payload with header", b"GET /api/hello.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + AUTH + b"\r\n")
elif MODE == "auth_split":
    show("auth split control", b"GET /api%2fexec%20?cmd=id HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + AUTH + b"\r\n")
    show("auth split payload Connection: authorization", b"GET /api%2fexec%20?cmd=id HTTP/1.1\r\nHost: alpha.test\r\nConnection: authorization\r\n" + AUTH + b"\r\n")
elif MODE == "expect":
    body = b"x" * 12 + b"\r\n"
    show("expect control no Expect", b"GET /api/f.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\nExpect: 100-continue\r\n\r\n")
    show("expect payload with Expect", b"GET /api/f.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\nExpect: 100-continue\r\n\r\n")
    show("expect rescue Connection: expect", b"GET /api/f.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: expect\r\nExpect: 100-continue\r\n\r\n")
elif MODE == "expect_body":
    body = b"GET /exec?cmd=id HTTP/1.1\r\nHost: x\r\n\r\n"
    show("expect exec control no Expect", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    show("expect exec with Expect only", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + EXPECT + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    show("expect exec rescue", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: expect\r\n" + EXPECT + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
elif MODE == "combined":
    body = b"GET /exec?cmd=id HTTP/1.1\r\nHost: x\r\n\r\n"
    show("combined control no extras", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: keep-alive\r\n" + AUTH + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    show("combined payload Expect deleted", b"POST /api/ HTTP/1.1\r\nHost: alpha.test\r\nConnection: expect\r\n" + EXPECT + AUTH + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
time.sleep(0.4)
lines = open(LOGFILE).read().splitlines()
print("UPSTREAM_SEGMENTS", len(lines) - start)
for index, line in enumerate(lines[start:], start):
    seg = json.loads(line)
    print(f"  [{index}] port={seg['port']} tokens={seg['tokens']} auth={seg['auth']} hdrs={seg['headers']}" +
          (f" exec={seg['exec']}" if "exec" in seg else ""))
    print(f"      reqline={seg['reqline']}")
    print(f"      hex={seg['hex']}")
    print(f"      bodyhex={seg['bodyhex']}")
