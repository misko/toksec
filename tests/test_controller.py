import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import controller
from evaluator import evaluate
from probe import GROUPS, response


PARTIAL_SERVER = '''import argparse
import os
import socket
from pathlib import Path

assert not Path(__CONTROLLER_PATH__).exists()
assert "OPENAI_API_KEY" not in os.environ
assert "HOME" not in os.environ
parser = argparse.ArgumentParser()
parser.add_argument("--host")
parser.add_argument("--port", type=int)
parser.add_argument("--root")
args = parser.parse_args()
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((args.host, args.port))
listener.listen(16)
while True:
    conn, _ = listener.accept()
    with conn:
        conn.settimeout(1)
        data = b""
        try:
            while b"\\r\\n\\r\\n" not in data and len(data) < 10000:
                part = conn.recv(4096)
                if not part:
                    break
                data += part
            if not data:
                continue
            code, body = 404, b""
            if data.startswith(b"GET /hello.txt "):
                code, body = 200, (Path(args.root) / "hello.txt").read_bytes()
            elif data.startswith(b"GET /empty.bin "):
                code, body = 200, b""
            head = (f"HTTP/1.1 {code} fixture\\r\\nContent-Length: {len(body)}"
                    "\\r\\nConnection: close\\r\\n\\r\\n").encode()
            conn.sendall(head + body)
        except (OSError, TimeoutError):
            pass
'''


def report(passed, median=None):
    groups = {g: g in passed for g in GROUPS}
    return {"groups": groups, "conformant": all(groups.values()), "cases": [],
            "performance": {"median": median} if median is not None else None}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name) / "pilot"
        controller.prepare(self.run)

    def tearDown(self):
        # Accepted artifact directories are deliberately not writable.
        for base, dirs, files in os.walk(self.temporary.name):
            Path(base).chmod(0o755)
        self.temporary.cleanup()

    def state(self):
        return json.loads((self.run / "state.json").read_text())

    def submit_report(self, value, source=b"print('candidate')\n"):
        (self.run / "workspace/server.py").write_bytes(source)
        with patch("controller.evaluate", return_value=value):
            return controller.submit(self.run)

    def test_prepare_is_empty_and_preserves_hard_budget(self):
        self.assertEqual(list((self.run / "workspace").iterdir()), [])
        manifest = json.loads((self.run / "manifest.json").read_text())
        self.assertEqual(manifest["configuration"]["budget_usd"], "5.00")
        self.assertEqual(manifest["configuration"]["service_tier"], "default")
        self.assertIn("HTTP Level 1 contract", (self.run / "launch-packet.md").read_text())
        self.assertFalse(controller.preflight(self.run)["launch_allowed"])

    def test_preparation_does_not_overwrite_a_run(self):
        with self.assertRaises(FileExistsError):
            controller.prepare(self.run)

    def test_no_artifact_is_reported_honestly(self):
        self.assertFalse(controller.export(self.run)["exported"])

    def test_nonrunnable_candidate_is_not_promoted(self):
        candidate = self.submit_report(report({"paths", "limits"}))
        self.assertFalse(candidate["selected"])
        self.assertIsNone(self.state()["best_partial"])

    def test_regression_cannot_trade_away_a_passed_group(self):
        first = self.submit_report(report({"bootstrap", "files"}))
        self.submit_report(report({"bootstrap", "paths", "limits"}))
        self.assertEqual(self.state()["best_partial"], first["candidate"])

    def test_conformance_beats_partial_and_performance_has_tolerance(self):
        self.submit_report(report({"bootstrap"}))
        full = self.submit_report(report(set(GROUPS), 100))
        self.submit_report(report(set(GROUPS), 105))
        self.assertEqual(self.state()["best_conformant"], full["candidate"])
        faster = self.submit_report(report(set(GROUPS), 120))
        self.assertEqual(self.state()["best_conformant"], faster["candidate"])
        self.submit_report(report({"bootstrap"}, 10000))
        self.assertEqual(self.state()["best_conformant"], faster["candidate"])

    def test_export_uses_archived_source_and_is_idempotent(self):
        first = self.submit_report(report({"bootstrap"}), b"accepted = True\n")
        (self.run / "workspace/server.py").write_text("unfinished = (\n")
        exported = controller.export(self.run)
        self.assertEqual(exported["candidate"], first["candidate"])
        self.assertEqual((Path(exported["artifact"]) / "server.py").read_bytes(), b"accepted = True\n")
        self.assertEqual(controller.export(self.run), exported)

    def test_atomic_pointer_failure_preserves_previous_state(self):
        self.submit_report(report({"bootstrap"}))
        before = (self.run / "state.json").read_bytes()
        with patch("controller.os.replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                controller.atomic_json(self.run / "state.json", {"invalid": "new state"})
        self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_changed_contract_blocks_existing_run(self):
        with patch("controller.fingerprints", return_value={"changed": "digest"}):
            with self.assertRaisesRegex(ValueError, "changed after preparation"):
                controller.export(self.run)

    def test_source_symlink_and_oversize_rejected(self):
        path = self.run / "workspace/server.py"
        path.symlink_to(self.run / "manifest.json")
        with self.assertRaises(OSError):
            controller.candidate_source(path)
        path.unlink()
        path.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            controller.candidate_source(path)

    def test_syntax_and_prohibited_library_fail_before_execution(self):
        directory = self.run / "workspace"
        (directory / "server.py").write_text("broken = (\n")
        self.assertFalse(evaluate(directory)["conformant"])
        (directory / "server.py").write_text("from http.server import HTTPServer\n")
        self.assertIn("prohibited", evaluate(directory)["error"])

    def test_socket_evaluation_and_broken_tail_preserve_incumbent(self):
        source = PARTIAL_SERVER.replace("__CONTROLLER_PATH__", repr(str(controller.ROOT / "controller.py")))
        (self.run / "workspace/server.py").write_text(source)
        first = controller.submit(self.run)
        self.assertIsNone(first["error"], first)
        self.assertTrue(first["groups"]["bootstrap"], first)
        self.assertFalse(first["conformant"])
        (self.run / "workspace/server.py").write_text("broken = (\n")
        rejected = controller.submit(self.run)
        self.assertFalse(rejected["selected"])
        self.assertEqual(self.state()["best_partial"], first["candidate"])
        self.assertEqual(controller.export(self.run)["outcome"], "working_partial")


class ProbeTests(unittest.TestCase):
    def test_response_requires_eof_payload_length_and_exact_bytes(self):
        good = b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\nabc"
        response(good, (200,), b"abc")
        for invalid in (good + b"x", good[:-1], good.replace(b"abc", b"xyz"),
                        good.replace(b"Content-Length: 3", b"Content-Length: 3\r\nContent-Length: 3")):
            with self.assertRaises(AssertionError):
                response(invalid, (200,), b"abc")


if __name__ == "__main__":
    unittest.main()
