# Capacity tool

`budget_status` accepts an empty JSON object. The controller binds the run directory. The model cannot select another run, change a balance, or reset the deadline.

`capacity.py` exports `TOOL_SPEC` and `bind_budget_status(run)`. `runner.py` dispatches the tool and injects a fresh snapshot before every inference request. These messages become part of the next request's counted input.

The response separates dollars, cumulative run tokens, context-window capacity, wall time, and accepted checkpoints. Unknown values are null. Context occupancy is not cumulative usage and remains unknown in this pilot.

Before a run starts, the controller reports the untouched dollar budget and an unstarted clock. Once the API runner initializes `ledger.json`, snapshots report settled token usage, outstanding reservations, and remaining allowance. Dollar spend is explicitly an upper bound at the pinned API rates. `usage_complete` is false when a reservation remains unresolved or usage is uncertain.

`can_start_model_call` means the run is eligible to attempt admission. It does not promise that the next request will fit. The runner counts that request and atomically reserves its input and maximum output before submitting inference. Pending requests, exhausted budgets, stopped runs, and the validation reserve prevent further admission.

The diagnostic wall clock uses the manifest's start time. The runner separately enforces the deadline with a monotonic clock and a process timer. Candidate reports supply conformance or performance work orders. The runner stops new inference during the final validation reserve and exports without another model call.

Inspect a fresh run:

```sh
python3 controller.py prepare --run .runs/capacity-demo
python3 controller.py budget-status --run .runs/capacity-demo
```

The model sees only three tools: `budget_status`, `submit_candidate`, and `finish`. Submission supplies a complete `server.py` string. The controller owns the output path, snapshot, sandbox execution, report, and promotion decision.
