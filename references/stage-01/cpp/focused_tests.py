#!/usr/bin/env python3
"""Additional contract checks, using only the Python standard library.

Run from the repository root with a compiled server and a new output directory.
These are independent local diagnostics, not replacements for the host API gate.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("server", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    server = str(args.server.resolve())
    checks = []
    with tempfile.TemporaryDirectory(prefix="toksec-check-") as temporary:
        base = Path(temporary)
        root = base / "www"
        root.mkdir()
        (root / "file").write_bytes(b"exact\x00bytes\xff")
        (root / "directory").mkdir()
        (root / "directory" / "child").write_bytes(b"nested")
        (root / "%2e%2e").write_bytes(b"once")
        (root / "café").write_bytes(b"UTF8")
        (root / "link").symlink_to("directory", target_is_directory=True)
        (root / "file-link").symlink_to("file")
        os.mkfifo(root / "fifo")
        unix = socket.socket(socket.AF_UNIX)
        unix.bind(str(root / "socket"))
        with (root / "large").open("wb") as large:
            large.truncate(16 * 1024 * 1024)
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        values = dict(listen=f"127.0.0.1:{port}", root=str(root), max_connections="256",
                      header_bytes="512", header_timeout_ms="250", idle_timeout_ms="300",
                      write_timeout_ms="350", max_requests="3", pipeline_depth="2")
        config = base / "server.conf"

        def config_text(settings):
            return "# custom configuration\n\n" + "".join(f"{k}={v}\n" for k, v in settings.items())

        config.write_text(config_text(values))
        process = subprocess.Popen([server, "--config", str(config)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            def connect():
                return socket.create_connection(("127.0.0.1", port), timeout=2)

            deadline = time.monotonic() + 2
            while True:
                try:
                    with connect():
                        break
                except OSError:
                    assert process.poll() is None, "server exited during startup"
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.01)

            def exchange(raw):
                with connect() as client:
                    client.sendall(raw)
                    data = b""
                    while True:
                        block = client.recv(65536)
                        if not block:
                            break
                        data += block
                header, body = data.split(b"\r\n\r\n", 1)
                lines = header.split(b"\r\n")
                status = int(lines[0].split(b" ")[1])
                headers = dict(line.lower().split(b":", 1) for line in lines[1:])
                assert headers[b"connection"].strip() == b"close"
                assert b"transfer-encoding" not in headers
                assert int(headers[b"content-length"]) == len(body)
                return status, body

            def request(target, fields=b"", method=b"GET"):
                return method + b" " + target + b" HTTP/1.1\r\n" + fields + b"\r\n"

            def check(name, raw, status, body=None):
                got, actual = exchange(raw)
                assert got == status, (name, got, status)
                if body is not None:
                    assert actual == body, (name, actual)
                checks.append(name)

            for target, body in [(b"/file", b"exact\x00bytes\xff"), (b"/directory/./child", b"nested"),
                                 (b"//directory//child", b"nested"), (b"/directory%2fchild", b"nested"),
                                 (b"/%252e%252e", b"once"), (b"/caf%C3%A9", b"UTF8"),
                                 (b"/caf\xc3\xa9", b"UTF8"), (b"/file?bad=%GG", b"exact\x00bytes\xff")]:
                check("valid-path-" + repr(target), request(target), 200, body)
            for target in (b"/%C0%AF", b"/%ED%A0%80", b"/%F4%90%80%80", b"/%E2%82", b"/bad\\name", b"/\xff"):
                check("invalid-path-" + repr(target), request(target), 400)
            for target in (b"/directory/../file", b"/%2e%2e", b"/link/child", b"/file-link", b"/fifo", b"/socket"):
                check("confinement-" + repr(target), request(target), 403)
            for fields in (b"Content-Length: +0\r\n", b"Content-Length: 0,0\r\n",
                           b"content-length: 00\r\nCONTENT-LENGTH: 0\r\n", b"TRANSFER-ENCODING:\r\n",
                           b"Bad Name: a\r\n", b"Name : a\r\n", b"A: b\x7f\r\n", b"\tX: a\r\n"):
                check("invalid-fields-" + repr(fields), request(b"/file", fields), 400)
            check("many-decimal-zeroes", request(b"/file", b"content-length: " + b"0" * 400 + b"\r\n"), 200)
            check("unknown-valid-method", request(b"/file", method=b"CUSTOM!"), 405)
            check("invalid-method", request(b"/file", method=b"GE\tT"), 400)
            check("invalid-version", b"GET /file HTTP/1.2\r\n\r\n", 400)
            for n, expected in [(512, 200), (513, 431)]:
                initial = b"GET /file HTTP/1.1\r\nX: "
                check(f"custom-header-limit-{n}", initial + b"a" * (n - len(initial) - 4) + b"\r\n\r\n", expected)

            silent = [connect() for _ in range(48)]
            start = time.monotonic()
            check("silent-clients-isolated", request(b"/file"), 200)
            assert time.monotonic() - start < 0.2
            for client in silent:
                assert client.recv(1024) == b"", "silent request deadline missing"
                client.close()
            assert time.monotonic() - start < 0.75
            checks.append("custom-silent-header-deadline")

            with connect() as client:
                start = time.monotonic()
                client.sendall(b"GET /file HTTP/1.1\r\nX: ")
                for _ in range(4):
                    time.sleep(0.08)
                    try:
                        client.sendall(b"a")
                    except OSError:
                        break
                assert client.recv(1024) == b""
                assert time.monotonic() - start < 0.65
            checks.append("custom-absolute-trickle-deadline")

            with connect() as client:
                client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
                client.sendall(request(b"/large"))
                client.shutdown(socket.SHUT_WR)
                time.sleep(0.05)
                start = time.monotonic()
                check("half-closed-slow-reader-isolated", request(b"/file"), 200)
                assert time.monotonic() - start < 0.2
                time.sleep(0.45)
                received = 0
                while True:
                    data = client.recv(65536)
                    if not data:
                        break
                    received += len(data)
                assert received < 16 * 1024 * 1024, "blocked output deadline missing"
            checks.append("custom-write-deadline")
            for i in range(300):
                got, body = exchange(request(b"/file"))
                assert got == 200 and body == b"exact\x00bytes\xff", i
            checks.append("300-fresh-requests-after-errors-and-timeouts")
        finally:
            process.terminate()
            process.wait(timeout=2)
            unix.close()

        variants = [dict(values, listen="127.0.0.1:65536"), dict(values, listen="127.0.0.1:-1"),
                    dict(values, max_connections="-1"), dict(values, pipeline_depth="1.0"),
                    dict(values, header_timeout_ms="0"), dict(values, root="relative"),
                    dict(values, write_timeout_ms=str(2**64))]
        for i, variant in enumerate(variants):
            config.write_text(config_text(variant))
            rejected = subprocess.run([server, "--config", str(config)], timeout=2,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert rejected.returncode != 0, variant
            checks.append(f"invalid-config-{i}")
    result = {"passed": True, "checks": checks, "count": len(checks),
              "scope": "independent local contract diagnostics; not a host API or performance claim"}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
