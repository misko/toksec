# Original Python HTTP pilot

This package preserves the original Level 1 Python experiment implementation.
Current Rust and C++ campaigns use `toksec`; the experimental TLS campaign uses
`stage10`. The pilot is retained for regression tests and historical inspection,
not as the default campaign path.

The package contains its controller, budget ledger, capacity tool, model loop,
sandbox evaluator, socket probe, prompts, configuration, and original task.
Shared atomic writes, HTTP transport, and pure token accounting live in
`toksec/storage.py`, `toksec/api.py`, and `toksec/metering.py`.

Run commands from the repository root:

```sh
python3 -m legacy.python_pilot.controller --help
python3 -m legacy.python_pilot.runner --help
python3 -m legacy.python_pilot.controller prepare --run .runs/pilot-example
python3 -m legacy.python_pilot.controller budget-status --run .runs/pilot-example
```

Preparation and status commands do not make model API calls. The runner's `run`
command can spend money and retains its original preflight and reservation rules.
This relocation does not authorize a paid campaign or update its price schedule.

Existing raw runs, ledgers, prompt packets, and published results are not modified.
Relocating modules changes the framework fingerprints. Reproduce a historical run
with its original recorded checkout; do not rewrite its manifest to bypass the
fingerprint check. New pilot preparations fingerprint this package and its shared
helpers.

The evaluator still executes the trusted `probe.py` directly in an isolated Python
interpreter inside the candidate network namespace. The probe requires only the
standard library and does not import the host package.
