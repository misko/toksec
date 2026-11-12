"""Run the Level 1 builder through a bounded Responses API tool loop."""

import argparse
import contextlib
import datetime
import fcntl
import json
import os
import signal
import time
import urllib.error
import urllib.request
from pathlib import Path

import controller
import metering
from capacity import TOOL_SPEC, budget_status


SUBMIT_TOOL = {
    "type": "function", "name": "submit_candidate",
    "description": "Replace server.py with complete source and evaluate it in the isolated sandbox. Returns promotion checks.",
    "parameters": {"type": "object", "properties": {"source": {"type": "string"}},
                   "required": ["source"], "additionalProperties": False}, "strict": True,
}
FINISH_TOOL = {
    "type": "function", "name": "finish", "description": "End the run and export the best validated artifact.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True,
}
TOOLS = [TOOL_SPEC, SUBMIT_TOOL, FINISH_TOOL]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirects are not allowed")


class Responses:
    def __init__(self, key):
        if not key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect())

    def post(self, endpoint, payload, timeout):
        request = urllib.request.Request("https://api.openai.com/v1/" + endpoint,
                                         data=json.dumps(payload).encode(),
                                         headers={"Authorization": "Bearer " + self.key,
                                                  "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"API HTTP {error.code}; no automatic retry") from None


def preflight(run):
    run = Path(run).resolve()
    with controller.locked(run):
        manifest = json.loads((run / "manifest.json").read_text())
    config = manifest["configuration"]
    reasons = []
    if not os.environ.get("OPENAI_API_KEY"):
        reasons.append("OPENAI_API_KEY is absent; existing Codex login is not configured for this API adapter")
    if (config["model"] != metering.MODEL or config["service_tier"] != "default"
            or config["budget_usd"] != "5.00" or config["token_limit"] != metering.TOKEN_LIMIT):
        reasons.append("unsupported pilot configuration")
    age = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.date.fromisoformat(metering.PRICE_DATE)).days
    if not 0 <= age <= 7:
        reasons.append("review and update the pinned price schedule before launch")
    if manifest["started_unix"] is not None or (run / "ledger.json").exists():
        reasons.append("run already started; automatic restart is disabled")
    import shutil
    for command in ("bwrap", "nsenter"):
        if not shutil.which(command):
            reasons.append(command + " is unavailable")
    return {"launch_allowed": not reasons, "reasons": reasons, "model": metering.MODEL,
            "service_tier": "default", "token_limit": metering.TOKEN_LIMIT,
            "budget_usd": "5.00", "backend": "responses_api",
            "model_access_verified": False}


def dispatch(run, name, arguments):
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if name in {"budget_status", "finish"}:
        if arguments:
            raise ValueError("this tool takes no arguments")
        return budget_status(run) if name == "budget_status" else {"finished": True}
    if name != "submit_candidate" or set(arguments) != {"source"}:
        raise ValueError("unknown tool or arguments")
    source = arguments["source"]
    if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
        raise ValueError("candidate source must be a string of at most 1 MiB")
    path = run / "workspace/server.py"
    temporary = path.with_suffix(".pending")
    temporary.write_text(source)
    os.replace(temporary, path)
    result = controller.submit(run)
    report = json.loads(Path(result["report"]).read_text())
    result.pop("report")
    result["cases"] = report["cases"]
    result["performance"] = report["performance"]
    state = json.loads((run / "state.json").read_text())
    phase = "performance" if state["best_conformant"] else "conformance"
    result["work_order"] = (controller.ROOT / "prompts" / (phase + ".md")).read_text()
    return result


@contextlib.contextmanager
def deadline(seconds):
    def expired(signum, frame):
        raise TimeoutError("run wall-time limit reached")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def run_loop(run, client, *, continue_reconciled=False):
    run = Path(run).resolve()
    with (run / ".runner.lock").open("a") as ownership:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if continue_reconciled:
            with controller.locked(run):
                ledger = metering.read_ledger(run)
                if ledger["state"] != "active" or any(r["state"] != "settled" for r in ledger["requests"]):
                    raise ValueError("continuation requires a reconciled active ledger")
        else:
            metering.initialize(run)
        manifest = json.loads((run / "manifest.json").read_text())
        config = manifest["configuration"]
        remaining_seconds = max(0.001, config["wall_seconds"] - (time.time() - manifest["started_unix"]))
        end = time.monotonic() + remaining_seconds
        packet = (run / "launch-packet.md").read_text()
        packet += ("\n\nThis runner exposes only budget_status, submit_candidate, and finish. "
                   "Use submit_candidate with the complete server.py source to write and test it. "
                   "The controller runs an external client in the sandbox and returns its report. "
                   "You have no shell or direct filesystem access. Call finish when satisfied. "
                   "Capacity snapshots report whether another call is eligible, not a guarantee of admission.")
        history = [{"role": "developer", "content": packet}]
        reason = "finished"
        try:
            with deadline(remaining_seconds):
                while True:
                    capacity = budget_status(run)
                    if not capacity["can_start_model_call"]:
                        reason = capacity["reason"]
                        break
                    history.append({"role": "user", "content": "Controller capacity: " + json.dumps(capacity)})
                    request = {"model": metering.MODEL, "input": history, "tools": TOOLS}
                    timeout = min(60, end - time.monotonic() - config["reserve_seconds"])
                    if timeout <= 0:
                        reason = "validation reserve reached"
                        break
                    count = client.post("responses/input_tokens", request, timeout)["input_tokens"]
                    request_id = metering.reserve(run, count)
                    response = client.post("responses", dict(request, max_output_tokens=metering.MAX_OUTPUT,
                                           service_tier="default", store=False, parallel_tool_calls=False,
                                           include=["reasoning.encrypted_content"]), timeout)
                    controller.atomic_json(run / ("response-" + request_id + ".json"), response)
                    metering.settle(run, request_id, response)
                    if response["status"] != "completed":
                        reason = "incomplete response"
                        break
                    history.extend(response["output"])
                    calls = [item for item in response["output"] if item["type"] == "function_call"]
                    if not calls:
                        reason = "model ended without a tool call"
                        break
                    if len(calls) != 1:
                        raise ValueError("expected one sequential tool call")
                    call = calls[0]
                    try:
                        result = dispatch(run, call["name"], json.loads(call["arguments"]))
                    except (ValueError, TypeError) as error:
                        result = {"error": str(error)}
                    if result.get("finished"):
                        break
                    history.append({"type": "function_call_output", "call_id": call["call_id"],
                                    "output": json.dumps(result)})
        except (Exception, KeyboardInterrupt) as error:
            reason = type(error).__name__ + ": " + str(error)
        finally:
            metering.stop(run, reason)
            result = controller.export(run)
            result.update(stop_reason=reason, capacity=budget_status(run))
            controller.atomic_json(run / "result.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run"))
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = preflight(args.run)
        if args.command == "preflight" or not status["launch_allowed"]:
            print(json.dumps(status, indent=2))
            return 0 if status["launch_allowed"] else 2
        result = run_loop(args.run, Responses(os.environ["OPENAI_API_KEY"]))
        print(json.dumps(result, indent=2))
        return 0 if result["exported"] else 1
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
