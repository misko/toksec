import json
import contextlib
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from stage10 import checks


class Stage10CheckerTests(unittest.TestCase):
    def wire(self, responses, action):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def serve():
            conn, _ = listener.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(responses)
            listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with checks.Connection("/unused", port=port) as conn:
                conn.send(checks.request_bytes())
                action(conn)
        finally:
            thread.join(2)
            listener.close()

    def test_pipelined_prefetch_keeps_second_response(self):
        def action(conn):
            self.assertEqual(conn.response()[::2], (200, b"one"))
            self.assertEqual(conn.response()[::2], (200, b"two"))
        self.wire(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\none"
                  b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\ntwo", action)

    def test_reject_ambiguous_and_truncated_responses(self):
        for raw in (b"Content-Length: 2\r\nContent-Length: 2\r\n\r\nhi",
                    b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
                    b"Content-Length: 5\r\n\r\nhi"):
            with self.subTest(raw=raw):
                def action(conn):
                    with self.assertRaises((AssertionError, checks.http.client.IncompleteRead)):
                        conn.response()
                self.wire(b"HTTP/1.1 200 OK\r\n" + raw, action)

    def test_head_does_not_consume_next_response(self):
        def action(conn):
            status, headers, body = conn.response("HEAD")
            self.assertEqual((status, headers["content-length"], body), (200, "123", b""))
            self.assertEqual(conn.response()[::2], (200, b"hi"))
        self.wire(b"HTTP/1.1 200 OK\r\nContent-Length: 123\r\n\r\n"
                  b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi", action)

    def test_upstream_chunked_and_revalidation_oracle(self):
        with checks.Upstreams(ports=(0,)) as upstream:
            port = upstream.servers[0].server_port
            with checks.Connection("/unused", port=port) as conn:
                conn.send(checks.request_bytes("/chunked/a", close=False))
                self.assertEqual(conn.response()[::2], (200, b"/chunked/a"))
                conn.send(checks.request_bytes("/revalidate/a", headers=(("If-None-Match", '"oracle-v1"'),)))
                self.assertEqual(conn.response()[::2], (304, b""))
            self.assertEqual(upstream.count("/revalidate/a"), 1)

    def test_upstream_chunked_upload(self):
        with checks.Upstreams(ports=(0,)) as upstream:
            with checks.Connection("/unused", port=upstream.servers[0].server_port) as conn:
                conn.send(checks.request_bytes("/echo", method="POST", headers=(("Transfer-Encoding", "chunked"),)) + b"3\r\nabc\r\n0\r\n\r\n")
                self.assertEqual(conn.response()[::2], (200, b"abc"))

    def test_partial_report_never_claims_final_eligibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "www/beta").mkdir(parents=True)
            (root / "www/hello.txt").write_bytes(b"hello")
            (root / "www/beta/hello.txt").write_bytes(b"beta")
            with patch.object(checks.Checker, "local"), patch.object(checks, "wait_ready"):
                report = checks.run(root, bootstrap=True)
            self.assertTrue(report["passed"])
            self.assertFalse(report["final_grade_eligible"])
            self.assertTrue(report["unimplemented_requirements"])
            self.assertEqual([c["id"] for c in report["cases"]], ["bootstrap"])

    def test_cli_reports_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            status = checks.main(["--mode", "api", "--fixtures", str(Path(tmp) / "missing"), "--output", str(output)])
            report = json.loads(output.read_text())
            self.assertEqual(status, 1)
            self.assertFalse(report["passed"])
            self.assertEqual(report["scope"], "checker-infrastructure-failure")

    def test_readiness_retries_and_has_a_deadline(self):
        with patch.object(checks.socket, "create_connection", side_effect=[ConnectionRefusedError(), Mock(__enter__=Mock(), __exit__=Mock())]) as connect:
            checks.wait_ready(.2)
            self.assertEqual(connect.call_count, 2)
        with patch.object(checks.socket, "create_connection", side_effect=ConnectionRefusedError()):
            with self.assertRaisesRegex(RuntimeError, "listener unavailable"):
                checks.wait_ready(.01)

    def test_full_smoke_has_distinct_http_case(self):
        checker = checks.Checker.__new__(checks.Checker)
        checker.cases = []
        with patch.object(checker, "local"), patch.object(checker, "persistent"), patch.object(checker, "expected"):
            checker.smoke()
        self.assertEqual([c["id"] for c in checker.cases], ["http-get", "https-get", "https-persistent", "proxy"])

    def test_orchestrator_config_exit_logs_and_empty_results(self):
        from stage10 import evaluate
        for config_code, empty in ((0, False), (7, False), (0, True)):
            with self.subTest(config_code=config_code, empty=empty), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                calls = []

                @contextlib.contextmanager
                def runtime(*args, **kwargs):
                    calls.append(kwargs)
                    log = root / 'ephemeral.log'
                    log.write_text('candidate output')
                    try:
                        yield {'pid': 123, 'log': log, 'process': Mock(wait=Mock(return_value=config_code))}
                    finally:
                        log.unlink()

                def driver(command, **kwargs):
                    bootstrap = '--bootstrap' in command
                    path = Path(command[command.index('--output') + 1])
                    path.write_text(json.dumps({'cases': [] if empty else [{'id': 'bootstrap' if bootstrap else 'http-get', 'passed': True}], 'passed': True}))
                    return Mock(stdout='', stderr='', returncode=0)

                with patch.object(evaluate.sandbox, 'running', runtime), patch.object(evaluate.subprocess, 'run', driver):
                    report = evaluate.evaluate(root / 'artifact', root / 'output')
                self.assertEqual(report['passed'], config_code == 0 and not empty)
                config_calls = [c for c in calls if c.get('wait_for_pid') is False]
                self.assertEqual(len(config_calls), 1)
                self.assertEqual(config_calls[0]['args'], ['--check-config', '/fixtures/config/nginx.conf'])
                for name in ('config', 'bootstrap', 'smoke'):
                    self.assertEqual((root / 'output' / (name + '-server.log')).read_text(), 'candidate output')


if __name__ == "__main__":
    unittest.main()
