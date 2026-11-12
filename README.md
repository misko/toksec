# Toksec

Prepare and evaluate budgeted agent implementations of network servers.

The first task is a restricted Level 1 HTTP static file server. The implementation workspace starts empty. Prompts for every development phase are in `prompts/`. The five-level roadmap is in `tasks/http/levels.md`.

## Prepare the Luna pilot

Run these commands from this repository:

```sh
python3 controller.py prepare --run .runs/luna-http-l1
python3 controller.py preflight --run .runs/luna-http-l1
```

The preparation command creates an empty workspace and a rendered launch packet. Preflight checks API credentials, the price snapshot, sandbox tools, and whether the run is fresh. Model access is checked by the first token-count request. The runner never substitutes a different model.

The pilot uses `gpt-6-luna`, standard processing, a 10,000,000-token limit, and a $5 model-inference limit. Total tokens include input and output. Cached input and reasoning are subsets. The token limit values every token at $0.50 per million, the highest applicable standard rate within the runner's short-context limit. Preparation costs and local compute are separate.

Configure `OPENAI_API_KEY` securely in the runner environment, then launch:

```sh
python3 runner.py run --run .runs/luna-http-l1
```

The runner reserves input plus at most 16,000 output tokens before each request. It stops admitting work after 14 minutes and enforces a 15-minute process deadline. Timeout or uncertain usage retains the reservation and stops the run. Every exit exports the best validated artifact if one exists. Runs cannot restart automatically.

Existing Codex ChatGPT login is not wired into this adapter. The native launcher exposes no enforceable per-request token allowance. ChatGPT-plan OAuth inference has a separate authorization flow and does not accept `max_output_tokens`. This package does not extract cached credentials or label post-response cancellation a hard cap. See `docs/budget.md`.

## Evaluate a candidate

Place `server.py` in the prepared workspace, then run:

```sh
python3 controller.py evaluate --run .runs/luna-http-l1
python3 controller.py status --run .runs/luna-http-l1
python3 controller.py export --run .runs/luna-http-l1
```

The evaluator requires Linux, Python 3, Bubblewrap, and `nsenter`. It runs the candidate in a private network and filesystem namespace. A trusted client enters only the user and network namespaces to test it. The candidate cannot see the evaluator or accepted archive through its filesystem. No host credentials or home directory are mounted.

The controller snapshots one Python source file. It archives candidate reports and updates the accepted pointer atomically. Failed evaluations preserve the previous artifact. Exports use archived bytes, not the current workspace. The API builder can only read capacity, submit complete source through a tool, and finish. It cannot run host commands or choose file paths. Only the evaluator executes generated code, inside the sandbox. Native subagents share the host filesystem and cannot enforce that separation.

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
- `docs/budget.md` describes token admission, accounting, and authentication constraints.
- `docs/capacity-tool.md` describes the `budget_status` tool and local handler. Use `python3 controller.py budget-status --run RUN` to inspect a newly prepared run. The API runner dispatches this tool and supplies a capacity snapshot before every model request.
