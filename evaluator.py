"""Launch an immutable candidate in a private Bubblewrap sandbox."""

import ast
import json
import os
import resource
import selectors
import signal
import subprocess
import tempfile
from pathlib import Path

from probe import GROUPS


ROOT = Path(__file__).resolve().parent


def failed(reason):
    return {"schema_version": 1, "groups": {g: False for g in GROUPS},
            "cases": [], "conformant": False, "performance": None, "error": reason}


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (15,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def fixtures_at(base):
    root = base / "www"
    root.mkdir()
    (root / "nested").mkdir()
    (base / "outside").mkdir()
    (root / "hello.txt").write_bytes(b"toksec-" + os.urandom(32).hex().encode() + b"\n")
    (root / "empty.bin").write_bytes(b"")
    (root / "small.bin").write_bytes(os.urandom(4096))
    (root / "large.bin").write_bytes(os.urandom(2 * 1024 * 1024))
    (root / "space name.txt").write_bytes(b"space\n")
    (root / "nested" / "item.txt").write_bytes(b"nested\n")
    (base / "outside" / "secret").write_bytes(os.urandom(32))
    (root / "escape").symlink_to("/outside/secret")
    (root / "inside-link").symlink_to("hello.txt")


def sandbox_info(fd, timeout=3):
    data = b""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while len(data) < 4096:
            if not selector.select(timeout):
                raise TimeoutError("sandbox did not report its child PID")
            block = os.read(fd, 4096)
            if not block:
                raise RuntimeError("sandbox exited before reporting its child PID")
            data += block
            try:
                return json.loads(data)["child-pid"]
            except json.JSONDecodeError:
                pass
    raise RuntimeError("invalid sandbox status")


def evaluate(candidate):
    candidate = Path(candidate).resolve()
    try:
        source = (candidate / "server.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if any(name.split(".")[0] in {"http", "wsgiref"} for name in names):
                return failed("prohibited server/protocol-library import")
    except (OSError, UnicodeError, SyntaxError) as error:
        return failed(f"candidate cannot compile: {error}")
    with tempfile.TemporaryDirectory(prefix="toksec-eval-") as temporary:
        base = Path(temporary)
        fixtures_at(base)
        read_fd, write_fd = os.pipe()
        process = None
        try:
            command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                       "--cap-drop", "ALL", "--info-fd", str(write_fd), "--clearenv",
                       "--setenv", "PATH", "/usr/bin:/bin",
                       "--setenv", "PYTHONDONTWRITEBYTECODE", "1"]
            for system in ("/usr", "/lib", "/lib64", "/bin"):
                if Path(system).exists():
                    command += ["--ro-bind", system, system]
            command += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                        "--ro-bind", str(candidate), "/candidate",
                        "--ro-bind", str(base / "www"), "/www",
                        "--ro-bind", str(base / "outside"), "/outside",
                        "--chdir", "/candidate", "--", "/usr/bin/python3", "-I", "-B",
                        "/candidate/server.py", "--host", "127.0.0.1", "--port", "8080", "--root", "/www"]
            with (base / "server.log").open("wb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, pass_fds=(write_fd,),
                                           preexec_fn=limits, start_new_session=True)
                os.close(write_fd)
                write_fd = None
                pid = sandbox_info(read_fd)
                client = subprocess.run([
                    "nsenter", "--target", str(pid), "--user", "--net", "--preserve-credentials",
                    "--", "/usr/bin/python3", "-I", "-B", str(ROOT / "probe.py"),
                    "--port", "8080", "--fixtures", str(base),
                ], capture_output=True, text=True, timeout=45)
                if client.returncode:
                    return failed("trusted probe failed: " + client.stderr[-1500:])
                report = json.loads(client.stdout)
                if set(report["groups"]) != set(GROUPS):
                    raise ValueError("invalid evaluator groups")
                return report
        except (OSError, ValueError, KeyError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
            return failed(f"evaluation failed: {error}")
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=3)
