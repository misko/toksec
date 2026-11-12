import argparse
import os
import re
import socket
import stat

MAX_HEADER = 8192
TOKEN = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
HEX = b"0123456789abcdefABCDEF"


def response(conn, status, body=b"", content_type=False):
    reasons = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout", 431: "Request Header Fields Too Large"}
    headers = [b"Content-Length: " + str(len(body)).encode("ascii"), b"Connection: close"]
    if content_type:
        headers.append(b"Content-Type: application/octet-stream")
    head = b"HTTP/1.0 %d %s\r\n%s\r\n\r\n" % (status, reasons[status].encode("ascii"), b"\r\n".join(headers))
    conn.sendall(head + body)


def drain_after_error(conn):
    try:
        conn.settimeout(0.2)
        while conn.recv(4096):
            pass
    except (socket.timeout, OSError):
        pass


def parse_request(data):
    end = data.find(b"\r\n\r\n")
    if end < 0:
        return None
    if end + 4 > MAX_HEADER:
        raise ValueError("large")
    head = data[:end]
    if b"\x00" in head:
        raise ValueError("bad")
    lines = head.split(b"\r\n")
    parts = lines[0].split(b" ")
    if len(parts) != 3 or not all(parts):
        raise ValueError("bad")
    method, target, version = parts
    if not TOKEN.fullmatch(method) or version not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise ValueError("bad")
    if any(c < 33 or c > 126 for c in target) or b"#" in target:
        raise ValueError("bad")
    for i, c in enumerate(target):
        if c == 37 and (i + 2 >= len(target) or target[i + 1] not in HEX or target[i + 2] not in HEX):
            raise ValueError("bad")
    if not target.startswith(b"/"):
        raise ValueError("bad")
    lengths = []
    transfer = False
    for line in lines[1:]:
        if not line or line[:1] in (b" ", b"\t") or b":" not in line:
            raise ValueError("bad")
        name, value = line.split(b":", 1)
        if not TOKEN.fullmatch(name):
            raise ValueError("bad")
        if any((c < 32 and c != 9) or c == 127 for c in value):
            raise ValueError("bad")
        lname = name.lower()
        if lname == b"transfer-encoding":
            transfer = True
        elif lname == b"content-length":
            lengths.append(value.strip(b" \t"))
    if transfer or len(lengths) > 1:
        raise ValueError("bad")
    if lengths and (not lengths[0] or not lengths[0].isdigit() or lengths[0] != b"0"):
        raise ValueError("bad")
    return method, target, version


def file_for_target(target, root):
    pathpart = target.split(b"?", 1)[0]
    raw = bytearray()
    i = 0
    while i < len(pathpart):
        if pathpart[i] == 37:
            raw.append(int(pathpart[i + 1:i + 3], 16))
            i += 3
        else:
            raw.append(pathpart[i])
            i += 1
    try:
        path = bytes(raw).decode("utf-8", "strict")
    except UnicodeDecodeError:
        return 400, None
    if "\x00" in path or "\\" in path:
        return 400, None
    comps = path.split("/")
    if ".." in comps:
        return 403, None
    trailing = path.endswith("/")
    current = root
    try:
        for component in comps:
            if component in ("", "."):
                continue
            current = os.path.join(current, component)
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                return 404, None
            if stat.S_ISLNK(info.st_mode):
                return 403, None
        if trailing:
            return 403, None
        info = os.lstat(current)
        if not stat.S_ISREG(info.st_mode):
            return 403, None
        with open(current, "rb") as f:
            return 200, f.read()
    except FileNotFoundError:
        return 404, None
    except (PermissionError, IsADirectoryError, OSError):
        return 403, None


def handle(conn, root):
    conn.settimeout(1.0)
    data = bytearray()
    try:
        while True:
            end = data.find(b"\r\n\r\n")
            if end >= 0:
                if end + 4 > MAX_HEADER:
                    response(conn, 431)
                    drain_after_error(conn)
                    return
                break
            if len(data) >= MAX_HEADER:
                response(conn, 431)
                drain_after_error(conn)
                return
            chunk = conn.recv(min(4096, MAX_HEADER - len(data)))
            if not chunk:
                return
            data.extend(chunk)
            for i, byte in enumerate(data):
                if byte == 10 and (i == 0 or data[i - 1] != 13):
                    response(conn, 400)
                    return
                if byte == 13 and i + 1 < len(data) and data[i + 1] != 10:
                    response(conn, 400)
                    return
        try:
            parsed = parse_request(bytes(data))
        except ValueError as e:
            response(conn, 431 if str(e) == "large" else 400)
            return
        if parsed is None:
            response(conn, 400)
            return
        method, target, _version = parsed
        if method != b"GET":
            response(conn, 405)
            return
        status, body = file_for_target(target, root)
        if status == 200:
            response(conn, 200, body, True)
        else:
            response(conn, status)
    except socket.timeout:
        return
    except (ConnectionError, OSError):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = os.path.realpath(args.root)
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    server = socket.socket(family, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(128)
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                handle(conn, root)
    finally:
        server.close()


if __name__ == "__main__":
    main()
