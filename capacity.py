"""Controller-owned capacity snapshots for the offline pilot."""

import json
import math
import time
from decimal import Decimal
from pathlib import Path


TOOL_SPEC = {
    "type": "function",
    "name": "budget_status",
    "description": (
        "Read the controller's remaining run capacity and accepted checkpoint. "
        "Unknown values are null. This read does not reserve capacity or authorize a model call."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}


def budget_status(run, *, now=None):
    from controller import accepted_groups, locked

    run = Path(run).resolve()
    with locked(run):
        manifest = json.loads((run / "manifest.json").read_text())
        state = json.loads((run / "state.json").read_text())
        config = manifest["configuration"]
        observed = time.time() if now is None else now
        if not math.isfinite(observed):
            raise ValueError("invalid controller clock snapshot")
        started = manifest["started_unix"]
        unstarted = started is None
        remaining = None
        if started is not None:
            if not math.isfinite(started) or not math.isfinite(observed) or observed < started:
                raise ValueError("invalid controller clock snapshot")
            remaining = max(0, config["wall_seconds"] - (observed - started))
        identity = state["best_conformant"] or state["best_partial"]
        passed = sorted(accepted_groups(run, identity))
        from probe import GROUPS

        # The offline controller cannot infer charges after an external model launch.
        known_zero = unstarted and manifest["model_calls"] == 0
        limit = Decimal(config["budget_usd"])
        if not limit.is_finite() or limit < 0:
            raise ValueError("invalid dollar budget")
        return {
            "schema_version": 1,
            "observed_unix": observed,
            "run_id": config["run_id"],
            "run_started": not unstarted,
            "accounting_status": "not_started" if known_zero else "unavailable",
            "dollars": {
                "limit": str(limit),
                "spent": "0.00" if known_zero else None,
                "reserved": "0.00" if known_zero else None,
                "remaining": str(limit) if known_zero else None,
            },
            "tokens": {"limit": None, "used": None, "reserved": None, "remaining": None},
            "context_window": {"limit_tokens": None, "used_tokens": None, "remaining_tokens": None},
            "time": {
                "limit_seconds": config["wall_seconds"],
                "remaining_seconds": remaining,
                "validation_reserve_seconds": config["reserve_seconds"],
                "work_seconds_remaining": None if remaining is None else max(0, remaining - config["reserve_seconds"]),
            },
            "checkpoint": {
                "best_partial": state["best_partial"],
                "best_conformant": state["best_conformant"],
                "validated_groups": passed,
                "missing_groups": sorted(set(GROUPS) - set(passed)),
            },
            "can_start_model_call": False,
            "recommended_action": "do_not_start",
            "reason": "No metered model adapter is connected. Capacity reporting does not enforce spending.",
        }


def bind_budget_status(run):
    """Bind the run on the trusted side; the model cannot select another run."""
    def handle(arguments):
        if not isinstance(arguments, dict) or arguments:
            raise ValueError("budget_status accepts an empty object only")
        return budget_status(run)
    return handle
