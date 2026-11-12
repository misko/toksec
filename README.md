# Toksec

Prepare and evaluate budgeted agent implementations of network servers.

The first task is a restricted Level 1 HTTP static file server. The implementation workspace starts empty. Prompts for every development phase are in `prompts/`. The five-level roadmap is in `tasks/http/levels.md`.

## Prepare the Luna pilot

Run these commands from this repository:

```sh
python3 controller.py prepare --run .runs/luna-http-l1
python3 controller.py preflight --run .runs/luna-http-l1
```

The preparation command creates an empty workspace and a rendered launch packet. Preflight intentionally refuses the native Luna launch. The available native agent interface has no per-run dollar cap or metered request admission. No API credentials or verified Luna API rate card were available during preparation. A `$5` prompt is not enforcement.

The requested model is `gpt-6-luna`, with a $5 model-inference limit and standard processing. Setup costs are separate and not measured by this harness. The proposed wall-time limit is 15 minutes after launch, including validation and export. This limit is recorded but requires the future model-run controller to enforce it. No model has been launched by this package.

An API-backed launch adapter still needs verified access to the requested model, verified pricing, pre-request reservations, exact usage settlement, and process-wide deadline enforcement. Do not substitute a different model or relax the budget silently.

## Evaluate a candidate

Place `server.py` in the prepared workspace, then run:

```sh
python3 controller.py evaluate --run .runs/luna-http-l1
python3 controller.py status --run .runs/luna-http-l1
python3 controller.py export --run .runs/luna-http-l1
```

The evaluator requires Linux, Python 3, Bubblewrap, and `nsenter`. It runs the candidate in a private network and filesystem namespace. A trusted client enters only the user and network namespaces to test it. The candidate cannot see the evaluator or accepted archive through its filesystem. No host credentials or home directory are mounted.

The controller snapshots one Python source file. It archives candidate reports and updates the accepted pointer atomically. Failed evaluations preserve the previous artifact. Exports use archived bytes, not the current workspace. These are controller-owned boundaries only when the future builder adapter exposes solely the workspace and approved tools. Native subagents share the host filesystem and cannot enforce that separation.

All current checks are development/promotion checks. There is no sealed final suite yet. `conformant` means passing the implemented promotion suite, not proof of complete correctness or security. Performance results are exploratory valid-goodput measurements. The first conformant artifact is retained on ties; later artifacts need at least a 10% median improvement across three short rounds.

## Verify the preparation

```sh
python3 -m unittest discover -s tests -v
```

Tests cover sandbox execution, real socket probes against a deliberately incomplete fixture, failed candidates, snapshot isolation, atomic pointer failures, and selection rules. The fixture is not a reference implementation and is not included in builder launch packets.

## Read the experiment documents

- `tasks/http/level-1.md` fixes the first task contract.
- `prompts/policy.md` fixes the builder policy.
- `prompts/launch.md` and `prompts/status.md` are controller-rendered templates.
- `prompts/bootstrap.md`, `prompts/conformance.md`, `prompts/performance.md`, and `prompts/stabilize.md` contain phase work orders.
- `prompts/handoff.md` describes agent replacement without losing state.
- `experiments/luna-http-l1.json` records the requested pilot configuration.
- `docs/budget.md` records the launch blocker and requirements for an enforceable adapter.
- `docs/capacity-tool.md` describes the `budget_status` tool and local handler. Use `python3 controller.py budget-status --run RUN` to inspect a newly prepared run. A model adapter still needs to wire the handler into its tool dispatcher.
