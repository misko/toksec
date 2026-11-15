"""Trusted socket client. Run in the candidate's network, not its mount namespace."""

import argparse
import json
import socket
import statistics
import time
from pathlib import Path


GROUPS = ("bootstrap", "files", "paths", "framing", "limits", "recovery")


def exchange(port, chunks, timeout=3):
    deadline = time.monotonic() + timeout
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        for chunk in chunks:
            sock.sendall(chunk)
            if len(chunks) > 1:
                time.sleep(0.01)
        response = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("response did not reach EOF before deadline")
            sock.settimeout(remaining)
            block = sock.recv(65536)
            if not block:
                return bytes(response)
            response.extend(block)
            if len(response) > 3 * 1024 * 1024:
                raise AssertionError("response exceeded 3 MiB")


def request(path, method=b"GET", version=b"HTTP/1.1", headers=b""):
    return method + b" " + path + b" " + version + b"\r\n" + headers + b"\r\n"


def response(raw, expected_status, expected_body=None):
    head, separator, body = raw.partition(b"\r\n\r\n")
    assert separator, "missing response header terminator"
    lines = head.split(b"\r\n")
    status = lines.pop(0).split(b" ", 2)
    assert len(status) >= 2 and status[0] in (b"HTTP/1.0", b"HTTP/1.1"), "invalid status line"
    assert int(status[1]) in expected_status, f"unexpected HTTP status {status[1]!r}"
    headers = {}
    for line in lines:
        key, colon, value = line.partition(b":")
        assert colon and key, "malformed response header"
        headers.setdefault(key.lower(), []).append(value.strip())
    lengths = headers.get(b"content-length", [])
    assert len(lengths) == 1 and lengths[0].isdigit(), "missing/duplicate/invalid Content-Length"
    assert int(lengths[0]) == len(body), "body length mismatch or multiple responses"
    assert headers.get(b"connection") == [b"close"], "Connection must be close"
    assert b"transfer-encoding" not in headers, "unsupported response transfer encoding"
    if expected_body is not None:
        assert body == expected_body, "incorrect file bytes"


def evaluate(port, fixtures):
    fixtures = Path(fixtures)
    results = []

    def check(group, name, action):
        try:
            action()
            results.append({"group": group, "name": name, "passed": True})
        except Exception as error:
            results.append({"group": group, "name": name, "passed": False,
                            "error": f"{type(error).__name__}: {error}"[:500]})

    def get(path, codes=(200,), body=None, **kwargs):
        response(exchange(port, [request(path, **kwargs)]), codes, body)

    ordinary = (fixtures / "www" / "hello.txt").read_bytes()
    small = (fixtures / "www" / "small.bin").read_bytes()
    check("bootstrap", "ordinary", lambda: get(b"/hello.txt", body=ordinary))
    check("bootstrap", "empty", lambda: get(b"/empty.bin", body=b""))
    check("bootstrap", "missing", lambda: get(b"/absent-file", codes=(404,)))
    check("files", "binary", lambda: get(b"/small.bin", body=small))
    check("files", "large", lambda: get(b"/large.bin", body=(fixtures / "www" / "large.bin").read_bytes()))
    check("files", "query", lambda: get(b"/hello.txt?ignored=1", body=ordinary))
    check("files", "escaped-space", lambda: get(b"/space%20name.txt", body=b"space\n"))
    check("files", "nested", lambda: get(b"/nested/item.txt", body=b"nested\n"))
    check("files", "http10", lambda: get(b"/hello.txt", body=ordinary, version=b"HTTP/1.0"))
    for name, path, codes in (
        ("directory", b"/nested/", (403,)),
        ("root", b"/", (403,)),
        ("traversal", b"/../outside/secret", (403,)),
        ("encoded-traversal", b"/%2e%2e/outside/secret", (403,)),
        ("symlink", b"/escape", (403,)),
        ("inside-symlink", b"/inside-link", (403,)),
        ("trailing-slash", b"/hello.txt/", (403, 404)),
        ("nul", b"/hello%00.txt", (400,)),
        ("bad-escape", b"/%xx", (400,)),
        ("bad-utf8", b"/%ff", (400,)),
        ("backslash", b"/a%5cb", (400,)),
    ):
        check("paths", name, lambda p=path, c=codes: get(p, codes=c))
    check("framing", "fragmented", lambda: response(
        exchange(port, [b"GE", b"T /hello.txt HT", b"TP/1.1\r\n", b"\r\n"]), (200,), ordinary))
    check("framing", "pipelined-closes", lambda: response(exchange(port, [
        request(b"/hello.txt") + request(b"/small.bin")]), (200,), ordinary))
    check("framing", "post", lambda: get(b"/hello.txt", codes=(405,), method=b"POST"))
    check("framing", "zero-body", lambda: get(b"/hello.txt", body=ordinary, headers=b"Content-Length: 0\r\n"))
    check("framing", "unknown-header", lambda: get(b"/hello.txt", body=ordinary, headers=b"X-Test: value\r\n"))
    for name, raw in (
        ("bad-version", request(b"/hello.txt", version=b"HTTP/9.9")),
        ("absolute-target", request(b"http://example.test/hello.txt")),
        ("fragment-target", request(b"/hello.txt#fragment")),
        ("bad-header", request(b"/hello.txt", headers=b"Broken header\r\n")),
        ("folded-header", request(b"/hello.txt", headers=b" X-Test: value\r\n")),
        ("nul-header", request(b"/hello.txt", headers=b"X-Test: a\x00b\r\n")),
        ("bad-header-name", request(b"/hello.txt", headers=b"X Test: value\r\n")),
        ("bare-lf", b"GET /hello.txt HTTP/1.1\n\n"),
        ("transfer-encoding", request(b"/hello.txt", headers=b"Transfer-Encoding: chunked\r\n")),
        ("duplicate-length", request(b"/hello.txt", headers=b"Content-Length: 0\r\ncOnTeNt-LeNgTh: 0\r\n")),
        ("body-not-supported", request(b"/hello.txt", headers=b"Content-Length: 1\r\n") + b"x"),
        ("invalid-length", request(b"/hello.txt", headers=b"Content-Length: nope\r\n")),
    ):
        check("framing", name, lambda r=raw: response(exchange(port, [r]), (400,)))
    check("limits", "oversized-header", lambda: response(exchange(port, [
        request(b"/hello.txt", headers=b"X-Big: " + b"a" * 8300 + b"\r\n")]), (431,)))

    def incomplete():
        raw = exchange(port, [b"GET /hello.txt HTTP/1.1\r\nX: unfinished"], timeout=2)
        if raw:
            response(raw, (408,))

    check("limits", "incomplete-deadline", incomplete)

    def disconnect():
        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.sendall(b"GET /large.bin HTTP/1.1\r\n\r\n")
        time.sleep(0.05)
        get(b"/hello.txt", body=ordinary)

    check("recovery", "client-disconnect", disconnect)
    check("recovery", "valid-after-errors", lambda: get(b"/hello.txt", body=ordinary))
    groups = {group: all(r["passed"] for r in results if r["group"] == group) for group in GROUPS}
    performance = None
    if all(groups.values()):
        rounds = []
        try:
            for _ in range(3):
                start = time.monotonic()
                for _ in range(100):
                    get(b"/small.bin", body=small)
                rounds.append(100 / (time.monotonic() - start))
            performance = {"metric": "valid_requests_per_second", "rounds": rounds,
                           "median": statistics.median(rounds), "requests_per_round": 100,
                           "file_bytes": len(small)}
        except Exception as error:
            results.append({"group": "recovery", "name": "benchmark-correctness", "passed": False,
                            "error": str(error)[:500]})
            groups["recovery"] = False
    return {"schema_version": 1, "groups": groups, "cases": results,
            "conformant": all(groups.values()), "performance": performance}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixtures", required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 2
    while True:
        try:
            with socket.create_connection(("127.0.0.1", args.port), timeout=0.1):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit("server did not become ready within two seconds")
            time.sleep(0.02)
    print(json.dumps(evaluate(args.port, args.fixtures)))
