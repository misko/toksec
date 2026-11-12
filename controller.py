"""Offline task preparation and checkpoint controller. Does not launch model calls."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path

from evaluator import evaluate
from probe import GROUPS


ROOT = Path(__file__).resolve().parent


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fingerprints():
    paths = [ROOT / "controller.py", ROOT / "capacity.py", ROOT / "evaluator.py", ROOT / "probe.py",
             ROOT / "tasks/http/level-1.md", ROOT / "experiments/luna-http-l1.json"]
    paths.extend(sorted((ROOT / "prompts").glob("*.md")))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def prepare(run):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    (run / "workspace").mkdir()
    (run / "candidates").mkdir()
    configuration = json.loads((ROOT / "experiments/luna-http-l1.json").read_text())
    configuration.update(run_id=run.name, workspace=str(run / "workspace"))
    packet = (ROOT / "prompts/launch.md").read_text().format(**configuration)
    for path in ("prompts/policy.md", "tasks/http/level-1.md", "prompts/bootstrap.md"):
        packet += "\n\n" + (ROOT / path).read_text()
    (run / "launch-packet.md").write_text(packet)
    atomic_json(run / "manifest.json", {"configuration": configuration, "fingerprints": fingerprints(),
                                       "prepared_unix": time.time(), "started_unix": None,
                                       "model_calls": 0, "model_spend_usd": "0.00"})
    atomic_json(run / "state.json", {"best_partial": None, "best_conformant": None, "last_candidate": None})
    return {"run": str(run), "launch_packet": str(run / "launch-packet.md"),
            "launch_status": configuration["launch_status"]}


@contextlib.contextmanager
def locked(run):
    with (run / ".controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = json.loads((run / "manifest.json").read_text())
        if manifest["fingerprints"] != fingerprints():
            raise ValueError("task/evaluator/prompt/config changed after preparation; prepare a new run")
        yield


def candidate_source(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise ValueError("server.py must be a regular file of at most 1 MiB")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            source = stream.read(1024 * 1024 + 1)
        if len(source) > 1024 * 1024:
            raise ValueError("server.py grew beyond 1 MiB")
        return source
    finally:
        os.close(fd)


def accepted_groups(run, identity):
    if identity is None:
        return set()
    report = json.loads((run / "candidates" / identity / "report.json").read_text())
    return {g for g, passed in report["groups"].items() if passed}


def select(run, state, identity, report):
    updated = dict(state, last_candidate=identity)
    passed = {g for g, okay in report["groups"].items() if okay}
    previous = accepted_groups(run, state["best_partial"])
    if "bootstrap" in passed and passed > previous:
        updated["best_partial"] = identity
    if report["conformant"]:
        incumbent = state["best_conformant"]
        if incumbent is None:
            updated["best_conformant"] = identity
        elif report["performance"] is not None:
            old = json.loads((run / "candidates" / incumbent / "report.json").read_text())
            if old["performance"] is None or report["performance"]["median"] >= old["performance"]["median"] * 1.1:
                updated["best_conformant"] = identity
        if updated["best_conformant"] == identity:
            updated["best_partial"] = identity
    return updated


def submit(run):
    run = Path(run).resolve()
    with locked(run):
        source = candidate_source(run / "workspace/server.py")
        digest = hashlib.sha256(source).hexdigest()
        identity = digest[:12] + "-" + uuid.uuid4().hex[:8]
        snapshot = run / "candidates" / identity
        snapshot.mkdir()
        (snapshot / "server.py").write_bytes(source)
        (snapshot / "server.py").chmod(0o444)
        report = evaluate(snapshot)
        report.update(candidate=identity, source_sha256=digest, evaluated_unix=time.time(),
                      measured_model_run=False)
        atomic_json(snapshot / "report.json", report)
        (snapshot / "report.json").chmod(0o444)
        snapshot.chmod(0o555)
        state = json.loads((run / "state.json").read_text())
        updated = select(run, state, identity, report)
        atomic_json(run / "state.json", updated)
        return {"candidate": identity, "conformant": report["conformant"], "groups": report["groups"],
                "selected": identity in (updated["best_partial"], updated["best_conformant"]),
                "error": report.get("error"), "report": str(snapshot / "report.json")}


def export(run):
    run = Path(run).resolve()
    with locked(run):
        state = json.loads((run / "state.json").read_text())
        identity = state["best_conformant"] or state["best_partial"]
        if identity is None:
            return {"outcome": "no_validated_runnable_artifact", "exported": False}
        destination = run / "exports" / identity
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            temporary = destination.parent / (".pending-" + uuid.uuid4().hex)
            shutil.copytree(run / "candidates" / identity, temporary)
            os.replace(temporary, destination)
        return {"outcome": "promotion_suite_conformant" if state["best_conformant"] else "working_partial",
                "exported": True, "artifact": str(destination), "candidate": identity,
                "sealed_final_evaluated": False}


def preflight(run):
    manifest = json.loads((Path(run) / "manifest.json").read_text())
    return {"launch_allowed": False, "model": manifest["configuration"]["model"],
            "budget_usd": manifest["configuration"]["budget_usd"], "service_tier": "default",
            "reason": "Native launcher has no enforceable dollar cap. A metered model adapter is not configured.",
            "api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
            "sandbox_tools": {name: shutil.which(name) is not None for name in ("bwrap", "nsenter")},
            "model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "preflight", "evaluate", "status", "budget-status", "export"))
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    from capacity import budget_status
    commands = {"prepare": prepare, "preflight": preflight, "evaluate": submit, "export": export,
                "budget-status": budget_status,
                "status": lambda p: json.loads((p / "state.json").read_text())}
    try:
        result = commands[args.command](args.run)
        print(json.dumps(result, indent=2))
        if args.command == "preflight" and not result["launch_allowed"]:
            return 2
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
