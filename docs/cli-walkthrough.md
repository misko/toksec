# Run, test and track an HTTP implementation

Run commands from the repository root. Python's standard library, rustc, gcc,
Bubblewrap and nsenter are required; performance testing needs five available
CPUs and an open-file hard limit of at least 16,384. All generated Rust compilation,
unit tests and server execution run in sandboxes. API credentials stay in the host
controller and are never mounted into a builder sandbox.

## Test an implementation without an LLM

```sh
python3 -m toksec check --level 1 --source starters/static.rs --output .runs/starter-check
python3 -m toksec check --level 2 --source /path/to/main.rs --output .runs/server-check --performance
```

Use a new output directory each time. `check` returns exit code 0 when all public
checks pass and 2 when the implementation fails. It writes compiler diagnostics
and per-case results to `result.json`. `--performance` runs the public benchmark
matrix only after all correctness checks pass. A partial starter is expected to
fail some checks; it is not a completed Stage 1 implementation.

## Create a campaign and independent runs

```sh
python3 -m toksec init --campaign .runs/terra-seeded --budget-usd 3
python3 -m toksec prepare --campaign .runs/terra-seeded --level 1 --model gpt-6.1-terra --wall-seconds 7200 --starter starters/static.rs
python3 -m toksec prepare --campaign .runs/terra-seeded --level 2 --model gpt-6.1-terra --wall-seconds 7200 --starter starters/static.rs
```

`--budget-usd` starts a new empty ledger, unlike legacy `init` which imports the
historical pilot. Keep old campaigns intact. Save the `run` paths printed by
`prepare`. Both stages get the same limited starter, independently compiled and
checked. Its source hash and retained candidate ID are recorded. Preparation does
not call the model. The two-hour limit applies to each run, while dollars are shared.

```sh
python3 -m toksec preflight --run RUN_PATH
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
python3 -m toksec status --campaign .runs/terra-seeded
python3 -m toksec report --run RUN_PATH
```

Run stages sequentially to avoid competing load generators. `prepare --spend-target-usd 0.10` stops Stage 1 after its settled spending reaches that target, leaving capacity for Stage 2. A call can cross this target; it is an allocation aid, not an additional hard cap. Terra uses medium
reasoning and standard processing. The existing conservative admission mechanism
reserves $2.745 per call: a $3 campaign can therefore stop far below $3 actual spend.
A two-hour limit is a ceiling, not a promise to continue when spending admission
blocks. Do not describe a token-count estimate as an unconditional billing cap.

## Inspect or drive individual iterations

```sh
python3 -m toksec submit --run RUN_PATH --source /path/to/main.rs
python3 -m toksec test --run RUN_PATH --source /path/to/rust-unit-tests.rs
python3 -m toksec revalidate --run RUN_PATH --target latest
python3 -m toksec benchmark --run RUN_PATH
python3 -m toksec report --run RUN_PATH > progress.md
python3 -m toksec export --run RUN_PATH
```

Use manual mutation commands only before the measured builder run, or in a separate
manual experiment; paid runs accept only their recorded starter as initial code.
`test` runs a supplied complete source with `rustc --test`. `revalidate` repeats
public checks through three fresh starts. `benchmark` compares the latest fully
accepted candidate against the retained one in alternating rounds. `export` records
the retained source location and limitations. `report` reads existing results without
running code or spending tokens, including after a framework upgrade.

The report shows passing-check counts, retained candidates and a table for every
completed benchmark: workload, median valid requests/second, worst p99 latency,
failed requests, eligibility and promotion. Immutable `benchmarks/*.json` files
preserve repeated measurements, their timestamp and budget position; they are never
overwritten by later measurements of the same candidate. `benchmark-progress.json`
contains the current matrix. Model-authored hypotheses are under `iterations/`.

## Interpret the benchmark

Both stages measure 4 KiB and 64 KiB responses at 256 and 4096 active clients.
Stage 1 uses fresh connections; Stage 2 also uses persistent connections. Each
workload has five rounds, a one-second warmup and three-second measurement window.
Metrics include exact-payload goodput, bytes/second, p50/p95/p99 latency, failures,
timeouts, actual server CPU/RSS and load-generator lag. Latency percentiles describe
successful requests; always read them alongside failures and timeouts.

The actual server executable is resolved by inode below the Bubblewrap supervisor.
The supervisor is still used to enter the network namespace. This fixes the older
runs' erroneous child-process rejection and supervisor CPU/RSS accounting.

An overloaded generator invalidates a performance claim. The current promotion gate
requires complete, eligible, error-free comparisons, no significant tail-latency
regression and a clear throughput gain. These gates remain conservative: correctness
fixes outside the public suite need new independent regressions before a reliable
promotion decision. Version 4 adds the previously discovered header parsing cases;
old version 3 results remain historical evidence, not comparable scores.

Run harness tests with `python3 -m unittest discover -s tests -v`.
