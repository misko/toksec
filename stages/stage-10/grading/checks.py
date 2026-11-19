"""Host-owned, deliberately partial Stage 10 black-box evaluation.

Run in the candidate network namespace with the host mount namespace intact.
This module never starts the candidate and is never included in builder input.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import http.client
import http.server
import json
from pathlib import Path
import socket
import ssl
import threading
import time
import uuid


TIMEOUT = 3.0
MAX_RESPONSE = 4 * 1024 * 1024
UPSTREAM_BODY = b"Stage 10 independent fixture upstream.\n"
PREFIX = b"p" * 65536
UNIMPLEMENTED = [
    "Complete configuration grammar, include bounds, diagnostics, inheritance and invalid TLS material matrix",
    "Atomic valid/invalid reload, certificate rotation and old-generation reservation/limiter behavior",
    "Worker count/replacement, SIGTERM draining, process-tree resource and sustained leak accounting",
    "Global rate/connection limits, FIFO queue saturation/expiry, retry/cooldown/probe fairness",
    "Cache byte/entry/waiter limits, coalescing, cancellation and all bypass/variant/revalidation combinations",
    "Full upstream malformed/truncated/informational/bodyless framing and timeout matrix",
    "Upload progress handshake, slow-reader resource bounds and all absolute deadlines",
    "TLS cipher/group exclusions, session resumption, fragmented handshake, close_notify and handshake admission bounds",
    "Filesystem symlink/nonregular confinement and binary/empty/large fixture matrix",
    "All configurable routing, alias, MIME, etag-off and keepalive-limit combinations",
]


def require(condition, explanation):
    if not condition:
        raise AssertionError(explanation)


def wait_ready(timeout=5.0):
    """Allow asynchronous master/worker listener startup before the first case."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 8080), timeout=min(.2, max(.001, deadline - time.monotonic()))):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(min(.05, max(0, deadline - time.monotonic())))
    raise RuntimeError(f"plaintext listener unavailable after {timeout}s: {last_error}")


class Connection:
    """Raw requests plus stdlib response decoding, with bounded reads/timeouts."""

    def __init__(self, fixtures, *, tls=False, host="alpha.test", version=None,
                 alpn=("h2", "http/1.1"), port=None):
        self.sock = socket.create_connection(("127.0.0.1", port or (8443 if tls else 8080)), TIMEOUT)
        try:
            if tls:
                ctx = ssl.create_default_context(cafile=str(Path(fixtures) / "tls/ca.pem"))
                ctx.set_alpn_protocols(list(alpn))
                ctx.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384")
                if version is not None:
                    ctx.minimum_version = ctx.maximum_version = version
                self.sock = ctx.wrap_socket(self.sock, server_hostname=host)
            self.sock.settimeout(TIMEOUT)
            self.reader = self.sock.makefile("rb")
        except BaseException:
            self.sock.close()
            raise

    def close(self):
        self.reader.close()
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, raw):
        self.sock.sendall(raw)

    def response(self, method="GET"):
        # Keep a single buffered file across pipelined responses. HTTPResponse
        # owns its own file normally, which can discard prefetched response bytes.
        reader = self.reader

        class Borrowed:
            def makefile(self, *args):
                class File:
                    def __getattr__(self, key):
                        return getattr(reader, key)

                    def close(self):
                        pass
                return File()

        response = http.client.HTTPResponse(Borrowed(), method=method)
        response.begin()
        headers = response.getheaders()
        lengths = [v for k, v in headers if k.lower() == "content-length"]
        encodings = [v for k, v in headers if k.lower() == "transfer-encoding"]
        require(len(lengths) <= 1, "duplicate response Content-Length")
        require(not (lengths and encodings), "ambiguous response framing")
        if lengths:
            require(lengths[0].isdigit(), "invalid response Content-Length")
            require(int(lengths[0]) <= MAX_RESPONSE, "response exceeds checker bound")
        body = response.read(MAX_RESPONSE + 1)
        require(len(body) <= MAX_RESPONSE, "response exceeds checker bound")
        if lengths and method != "HEAD" and response.status not in (204, 304):
            require(len(body) == int(lengths[0]), "truncated response")
        return response.status, {k.lower(): v for k, v in headers}, body


def request_bytes(path="/hello.txt", *, method="GET", host="alpha.test", close=True, headers=()):
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}"]
    lines.extend(f"{k}: {v}" for k, v in headers)
    lines.append("Connection: close" if close else "Connection: keep-alive")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


class Upstreams:
    """Bounded host-owned fixture service; endpoint counts are oracle state."""

    def __init__(self, ports=(8081, 8082)):
        self.ports = ports
        self.servers = []
        self.threads = []
        self.counts = collections.Counter()
        self.lock = threading.Lock()
        self.prefix_ack = threading.Event()

    def count(self, path):
        with self.lock:
            return self.counts[path]

    def __enter__(self):
        owner = self

        class Server(http.server.ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True
            slots = threading.BoundedSemaphore(32)

            def process_request(self, request, client_address):
                if not self.slots.acquire(blocking=False):
                    request.close()
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    self.slots.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.slots.release()

            def handle_error(self, *args):
                pass

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                self.request.settimeout(TIMEOUT)
                super().setup()

            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                with owner.lock:
                    owner.counts[self.path] += 1
                if self.path.startswith("/stream/"):
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(PREFIX) + 4))
                    self.end_headers()
                    self.wfile.write(PREFIX)
                    self.wfile.flush()
                    if owner.prefix_ack.wait(2):
                        self.wfile.write(b"done")
                    self.close_connection = True
                    return
                cacheable = self.path.startswith(("/cache/", "/revalidate/"))
                status = 304 if self.path.startswith("/revalidate/") and self.headers.get("If-None-Match") == '"oracle-v1"' else 200
                body = UPSTREAM_BODY if self.path == "/hello" else self.path.encode()
                self.send_response(status)
                if cacheable:
                    self.send_header("Cache-Control", "public,max-age=" + ("1" if self.path.startswith("/revalidate/") else "60"))
                    self.send_header("ETag", '"oracle-v1"')
                if self.path.startswith("/chunked/"):
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
                else:
                    self.send_header("Content-Length", str(len(body) if status == 200 else 0))
                    self.end_headers()
                    if status == 200 and self.command != "HEAD":
                        self.wfile.write(body)

            def do_POST(self):
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    body = bytearray()
                    while True:
                        line = self.rfile.readline(128)
                        size = int(line.strip().split(b";", 1)[0], 16)
                        if not size:
                            require(self.rfile.readline(8192) == b"\r\n", "unexpected trailer")
                            break
                        require(len(body) + size <= MAX_RESPONSE, "fixture upload limit")
                        body.extend(self.rfile.read(size))
                        require(self.rfile.read(2) == b"\r\n", "invalid fixture chunk")
                    body = bytes(body)
                else:
                    size = int(self.headers.get("Content-Length", "0"))
                    require(0 <= size <= MAX_RESPONSE, "fixture upload limit")
                    body = self.rfile.read(size)
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            for port in self.ports:
                server = Server(("127.0.0.1", port), Handler)
                self.servers.append(server)
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
                thread.start()
                self.threads.append(thread)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *args):
        self.prefix_ack.set()
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=1)


class Checker:
    def __init__(self, fixtures):
        self.fixtures = Path(fixtures)
        self.hello = (self.fixtures / "www/hello.txt").read_bytes()
        self.beta = (self.fixtures / "www/beta/hello.txt").read_bytes()
        self.cases = []

    def case(self, name, action):
        start = time.monotonic()
        try:
            action()
        except Exception as exc:
            self.cases.append(dict(id=name, passed=False, explanation=f"{type(exc).__name__}: {exc}"[:1000], seconds=round(time.monotonic() - start, 4)))
        else:
            self.cases.append(dict(id=name, passed=True, explanation="Observed expected wire behavior", seconds=round(time.monotonic() - start, 4)))

    def exchange(self, raw=None, *, method="GET", **kwargs):
        with Connection(self.fixtures, **kwargs) as conn:
            conn.send(raw or request_bytes(method=method))
            return conn.response(method)

    def local(self, *, tls=False):
        with Connection(self.fixtures, tls=tls) as conn:
            conn.send(request_bytes())
            status, headers, body = conn.response()
            require(status == 200 and body == self.hello, "ordinary GET representation differs")
            require(headers.get("content-length") == str(len(self.hello)), "missing/excess Content-Length")
            require(headers.get("connection", "").lower() == "close", "close not advertised")
            require(conn.reader.read(1) == b"", "transport did not close")

    def persistent(self, *, pipeline=False):
        with Connection(self.fixtures, tls=True) as conn:
            first = request_bytes(close=False)
            second = request_bytes()
            conn.send(first + second if pipeline else first)
            status, headers, body = conn.response()
            require(status == 200 and body == self.hello, "first persistent response differs")
            require(headers.get("connection", "").lower() == "keep-alive", "persistence not advertised")
            if not pipeline:
                conn.send(second)
            require(conn.response()[::2] == (200, self.hello), "second persistent response differs")

    def expected(self, raw, status, body=None, **kwargs):
        actual, headers, data = self.exchange(raw, **kwargs)
        require(actual == status, f"expected {status}, received {actual}")
        if body is not None:
            require(data == body, "representation bytes differ")
        return headers

    def smoke(self, bootstrap=False):
        self.case("bootstrap" if bootstrap else "http-get", self.local)
        if bootstrap:
            return
        self.case("https-get", lambda: self.local(tls=True))
        self.case("https-persistent", self.persistent)
        self.case("proxy", lambda: self.expected(request_bytes("/proxy/hello"), 200, UPSTREAM_BODY))

    def api(self, upstream):
        self.case("https-pipeline", lambda: self.persistent(pipeline=True))
        malformed = {
            "missing-host": b"GET / HTTP/1.1\r\n\r\n",
            "duplicate-host": b"GET / HTTP/1.1\r\nHost: alpha.test\r\nHost: alpha.test\r\n\r\n",
            "bare-lf": b"GET / HTTP/1.1\nHost: alpha.test\n\n",
            "folded-header": b"GET / HTTP/1.1\r\nHost: alpha.test\r\n x: y\r\n\r\n",
            "invalid-header-token": b"GET / HTTP/1.1\r\nHost: alpha.test\r\nbad name: x\r\n\r\n",
            "nul-value": b"GET / HTTP/1.1\r\nHost: alpha.test\r\nx: \x00\r\n\r\n",
        }
        for name, raw in malformed.items():
            def reject(raw=raw):
                with Connection(self.fixtures) as conn:
                    conn.send(raw)
                    require(conn.response()[0] == 400, "malformed request not rejected with 400")
                    require(conn.reader.read(1) == b"", "malformed request connection not closed")
            self.case("parse-" + name, reject)
        for host in ("unknown.test", "alpha.test.", "127.0.0.1", "alpha.test:0"):
            self.case("host-" + host, lambda host=host: self.expected(request_bytes(host=host), 400))
        self.case("host-normalization", lambda: self.expected(request_bytes(host="ALPHA.TEST:8080"), 200, self.hello))
        self.case("http10-default", lambda: self.expected(b"GET /hello.txt HTTP/1.0\r\n\r\n", 200, self.hello))
        self.case("unknown-method", lambda: self.expected(request_bytes(method="FROBNICATE"), 405))
        self.case("expect", lambda: self.expected(request_bytes(headers=(("Expect", "100-continue"),)), 417))
        for path, status in (("/%zz", 400), ("/%ff", 400), ("/hello.txt#x", 400), ("/%00", 400), ("/%5c", 400), ("/../hello.txt", 403), ("/%2e%2e/hello.txt", 403), ("http://alpha.test/", 400), ("/does-not-exist", 404)):
            self.case("path-" + path, lambda path=path, status=status: self.expected(request_bytes(path), status))
        self.case("path-normalization", lambda: self.expected(request_bytes("//./hello.txt?ignored=1"), 200, self.hello))
        for name, headers in (("duplicate-length", (("Content-Length", "0"), ("Content-Length", "0"))), ("nonzero-local-body", (("Content-Length", "1"),)), ("local-chunked", (("Transfer-Encoding", "chunked"),)), ("ambiguous-proxy", (("Content-Length", "0"), ("Transfer-Encoding", "chunked")))):
            self.case("framing-" + name, lambda name=name, headers=headers: self.expected(request_bytes("/proxy/hello" if name == "ambiguous-proxy" else "/hello.txt", headers=headers), 400))
        self.case("local-zero-length", lambda: self.expected(request_bytes(headers=(("Content-Length", "0"),)), 200, self.hello))
        self.case("header-limit", lambda: self.expected(request_bytes(headers=(("X-Large", "x" * 17000),)), 431))
        self.case("head", lambda: require(self.expected(request_bytes(method="HEAD"), 200, b"", method="HEAD").get("content-length") == str(len(self.hello)), "HEAD length differs"))
        for value, status, body, content_range in (("bytes=1-3", 206, self.hello[1:4], f"bytes 1-3/{len(self.hello)}"), ("bytes=-4", 206, self.hello[-4:], f"bytes {len(self.hello)-4}-{len(self.hello)-1}/{len(self.hello)}"), ("bytes=99999-", 416, None, f"bytes */{len(self.hello)}"), ("bytes=0-1,3-4", 400, None, None)):
            def ranged(value=value, status=status, body=body, content_range=content_range):
                headers = self.expected(request_bytes(headers=(("Range", value),)), status, body)
                if content_range:
                    require(headers.get("content-range") == content_range, "Content-Range differs")
            self.case("range-" + value, ranged)
        def conditional():
            etag = self.expected(request_bytes(), 200, self.hello).get("etag", "")
            require(len(etag) >= 2 and etag.startswith('"') and etag.endswith('"'), "missing quoted ETag")
            require(self.expected(request_bytes(), 200).get("etag") == etag, "unstable ETag")
            headers = self.expected(request_bytes(headers=(("If-None-Match", etag), ("Range", "bytes=0-1"))), 304, b"")
            require(headers.get("etag") == etag and headers.get("content-length") == "0", "conditional representation headers differ")
        self.case("conditional-before-range", conditional)
        for host, body in (("alpha.test", self.hello), ("beta.test", self.beta)):
            for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
                def tls_case(host=host, body=body, version=version):
                    with Connection(self.fixtures, tls=True, host=host, version=version) as conn:
                        require(conn.sock.selected_alpn_protocol() == "http/1.1", "ALPN selection differs")
                        conn.send(request_bytes(host=host))
                        require(conn.response()[::2] == (200, body), "SNI/HTTP representation differs")
                self.case(f"tls-{host}-{version.name}", tls_case)
        self.case("sni-host-independent", lambda: self.expected(request_bytes(host="beta.test"), 200, self.beta, tls=True))
        self.case("tls-no-alpn", lambda: self.expected(request_bytes(), 200, self.hello, tls=True, alpn=()))
        def bad_alpn():
            try:
                with Connection(self.fixtures, tls=True, alpn=("h2",)):
                    pass
            except ssl.SSLError as exc:
                require("NO_APPLICATION_PROTOCOL" in str(exc), "wrong TLS rejection alert")
            else:
                raise AssertionError("unsupported ALPN accepted")
        self.case("tls-reject-h2-only", bad_alpn)
        self.case("proxy-uri-query", lambda: self.expected(request_bytes("/proxy/echo?q=1"), 200, b"/echo?q=1"))
        self.case("proxy-chunked-response", lambda: self.expected(request_bytes("/proxy/chunked/body"), 200, b"/chunked/body"))
        self.case("proxy-chunked-upload", lambda: self.expected(request_bytes("/proxy/echo", method="POST", headers=(("Transfer-Encoding", "chunked"),)) + b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n", 200, b"abcde"))
        def cache(revalidate=False):
            path = ("/revalidate/" if revalidate else "/cache/") + uuid.uuid4().hex
            # One persistent connection stays on one worker, avoiding assumptions
            # about how independent connections are distributed among workers.
            with Connection(self.fixtures) as conn:
                for iteration in range(2):
                    if iteration and revalidate:
                        time.sleep(1.1)
                    conn.send(request_bytes("/proxy" + path, close=False))
                    require(conn.response()[::2] == (200, path.encode()), "cache representation differs")
            require(upstream.count(path) == (2 if revalidate else 1), "unexpected upstream fetch count")
        self.case("cache-hit-one-worker", cache)
        self.case("cache-etag-revalidation", lambda: cache(True))
        def stream():
            upstream.prefix_ack.clear()
            with Connection(self.fixtures) as conn:
                conn.send(request_bytes("/proxy/stream/progress"))
                conn.sock.settimeout(1)
                started = time.monotonic()
                # Parse headers manually to acknowledge body before EOF.
                status = conn.reader.readline(8192)
                require(status.split()[1] == b"200", "stream status differs")
                headers = {}
                for _ in range(100):
                    line = conn.reader.readline(8192)
                    if line == b"\r\n":
                        break
                    key, value = line.split(b":", 1)
                    headers[key.lower()] = value.strip()
                else:
                    raise AssertionError("stream header bound exceeded")
                require(headers.get(b"content-length") == str(len(PREFIX) + 4).encode(), "known stream length not preserved")
                require(b"transfer-encoding" not in headers, "ambiguous stream framing")
                require(conn.reader.read(len(PREFIX)) == PREFIX, "stream prefix differs")
                require(time.monotonic() - started < 1, "stream prefix exceeded one second")
                upstream.prefix_ack.set()
                require(conn.reader.read(4) == b"done", "stream tail differs")
        self.case("proxy-download-progress", stream)
        self.case("service-after-malformed", self.local)


def run(fixtures, mode="smoke", bootstrap=False):
    checker = Checker(fixtures)
    wait_ready()
    context = contextlib.nullcontext() if bootstrap else Upstreams()
    with context as upstream:
        checker.smoke(bootstrap)
        if mode == "api" and not bootstrap:
            checker.api(upstream)
    return dict(mode=mode, scope="bootstrap-only" if bootstrap else "partial-black-box-api" if mode == "api" else "visible-runtime-smoke; config validation is performed by parent",
                cases=checker.cases, passed=bool(checker.cases) and all(case["passed"] for case in checker.cases),
                unimplemented_requirements=list(UNIMPLEMENTED), final_grade_eligible=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "api"), required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.fixtures, args.mode, args.bootstrap)
    except Exception as exc:
        result = dict(mode=args.mode, scope="checker-infrastructure-failure", passed=False,
                      cases=[], error=f"{type(exc).__name__}: {exc}",
                      unimplemented_requirements=list(UNIMPLEMENTED), final_grade_eligible=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
