# Capacity tool

`budget_status` takes an empty JSON object. The controller binds the run directory before exposing the tool. The model cannot supply a path, change a balance, reset the deadline, or select another run.

`capacity.py` exports `TOOL_SPEC`, a provider-neutral function declaration, and `bind_budget_status(run)`, its local handler. A future model adapter must translate the declaration into its provider's tool format and dispatch calls to the bound handler. No model connection is included yet.

The result contains separate dollar, cumulative run-token, context-window, and wall-time fields. It also includes the validation reserve and the accepted checkpoint. Currency uses decimal strings. Unknown values are JSON null.

Before launch, the offline controller knows that no model calls have occurred and reports the untouched dollar budget. It does not report an unstarted clock as a running deadline. After an external launch, it cannot measure spend and returns unknown balances. The native pilot always returns `can_start_model_call: false` until a metered adapter exists. A configured budget is not evidence of metering.

The current wall-time snapshot uses the controller's Unix start time and rejects clocks earlier than that start. The future execution controller must enforce its own monotonic deadline. This diagnostic snapshot is not a deadline enforcer.

## Invoke the local handler

Prepare a new run after changing controller code or prompts, then inspect capacity:

```sh
python3 controller.py prepare --run .runs/capacity-demo
python3 controller.py budget-status --run .runs/capacity-demo
```

An adapter can dispatch the declared tool without accepting model-supplied paths:

```python
from capacity import TOOL_SPEC, bind_budget_status

handle = bind_budget_status(controller_owned_run_directory)
result = handle({})
```

## Integrate reporting with enforcement

The metered adapter must report spent and reserved amounts from the same authoritative ledger it uses to admit requests. Remaining allowance excludes outstanding reservations. It must count the status tool call and its response in the next request's token accounting. Reporting is not free model inference.

Attach a compact capacity snapshot to ordinary tool results as well, so forgetting an explicit status call does not leave the agent without updates. The controller must still check admission before every paid call and bound tool execution before dispatch. A positive status snapshot can become stale and never replaces atomic request reservation.

The phase recommendation should come from controller state. Use conformance while mandatory behavior is missing, performance only after acceptance, stabilization when the validation reserve is reached, and stop when a limit is exhausted. These live transitions remain part of the future execution adapter. The offline pilot reports `do_not_start`.
