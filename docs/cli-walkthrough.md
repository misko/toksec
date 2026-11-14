# Run, test and track an HTTP implementation

Run commands from the repository root. Python's standard library, rustc, gcc,
Bubblewrap and nsenter are required; performance testing needs five available
CPUs and an open-file hard limit of at least 16,384. All generated Rust compilation,
unit tests and server execution run in sandboxes. API credentials stay in the host
controller and are never mounted into a builder sandbox.

## One evaluation entry point

```sh
./evaluate.py --section api --level 1 --source /path/to/main.rs
./evaluate.py --section performance --level 2 --source /path/to/main.rs
./evaluate.py --section performance --run RUN_PATH
```

With `main.rs` and an `evaluation.json` containing `{"level": 1}` in the current
working directory, the short forms are `./evaluate.py --section api` and
`./evaluate.py --section performance`. The script needs this repository's Python
modules; it is not a standalone file to copy to an otherwise empty machine.
Use `--output NEW_DIRECTORY` for a chosen results location. Otherwise each call
creates a unique directory under `evaluation-results/` and prints its location.

The `api` section compiles with the prescribed optimized Rust build, then runs
all independent checks for the chosen level. Stage 1 currently has 12 cases covering
startup/configuration, byte-exact static GET responses, paths and percent decoding,
root confinement, fragmented requests, parsing and framing errors, header limits,
absolute deadlines, and recovery after disconnects. Stage 2 has 21 cases: shared file-serving checks plus HEAD,
persistence, ordered pipelining, connection limits/deadlines and independent
concurrent service. Each result identifies the failing case and its diagnostics.
No starter is supplied.

The `performance` section first runs the same API suite. Only a fully passing
implementation reaches the complete benchmark matrix described below. A successful
measurement does not mean performance is maximal. It provides evidence for the
next optimization. Local measurements do not automatically publish Git tags or
promote an incumbent. Paired campaign measurements use `benchmark_candidate`.

Exit codes: 0 means the requested section passed; 1 means an evaluator error;
2 means build/API failure; 3 means performance results are missing, ineligible or
contain request failures. `result.json` contains compiler diagnostics, per-case
results and, when eligible to run, benchmark rounds and summaries. API results and
completed workloads are saved incrementally; interruption can leave a partial
report, which is not a completed performance result.

With `--run`, the source is extracted from the latest completed release tag, never
from an uncommitted working tree. Grading requires the original evaluator
fingerprint; use the original framework checkout for older runs.

## What the sandboxed builder receives

Each independent run supplies the assembled [shared rules and selected stage documents](stage-layout.md), exact configuration, resource limits, acceptance-check descriptions and workload parameters. No Rust source or executable checker implementation is injected into its context. The controller supplies remaining capacity and bounded execution tools.

The current agent has bounded tools, not a general shell. `submit_candidate`
compiles and runs the API suite; `revalidate_candidate` repeats it across three
fresh starts; `benchmark_candidate` runs the performance matrix and paired
comparison. These use the same sandbox and public suite as `evaluate.py`.
`run_tests` permits additional Rust tests. `budget_status`, `record_iteration`,
`init_repository` and `release_candidate` provide capacity, experiment history
and durable Git submissions. The CLI is the human/automation entry point outside
the sandbox; copying it alone into the server sandbox would not provide a usable
agent shell or nested sandbox controller.

The agent chooses how to develop and test. It must publish periodic working Git tags; the last completed tag is graded. Continued improvement is requested until the finalization window or exhausted admission capacity. See [RULES.md](../RULES.md) for the authoritative policy.

## Create a campaign and independent runs

```sh
python3 -m toksec init --campaign .runs/terra-from-scratch --budget-usd 3
python3 -m toksec prepare --campaign .runs/terra-from-scratch --level 1 --model gpt-6.1-terra --wall-seconds 7200
python3 -m toksec prepare --campaign .runs/terra-from-scratch --level 2 --model gpt-6.1-terra --wall-seconds 7200
```

The CLI defaults to a new $3 ledger. Keep old campaigns intact. Save the run paths
printed by prepare. Both stages start empty; supplying --starter is rejected for
Stages 1 and 2. Preparation makes no model calls. The two-hour ceiling applies to
each run, while dollars are shared.

```sh
python3 -m toksec preflight --run RUN_PATH
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
python3 -m toksec status --campaign .runs/terra-from-scratch
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
manual experiment; measured Stage 1 and 2 runs must start with no candidates.
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

## Publish and grade Git releases

The builder can be stopped at any time. The graded submission is the last completed
`release/NNNNNN` tag in its private Git repository. Untagged edits and the retained
performance incumbent do not change that submission.

```sh
python3 -m toksec init-repository --run RUN_PATH
python3 -m toksec release --run RUN_PATH --note 'Complete file decoding and framing'
python3 -m toksec releases --run RUN_PATH
python3 -m toksec grade --run RUN_PATH --output .runs/grade-001 --performance
```

`init-repository` creates a new Git repository inside a Bubblewrap sandbox and
publishes the first validated snapshot. `release` publishes the latest candidate.
It must compile, pass bootstrap and retain all checks passed by the preceding
release. Tags are sequential and never force-updated. Repeating publication of the
same source returns the existing release.

`grade` extracts the latest tag, checks its source hash, then compiles and runs the
public suite in a new sandbox. `--performance` measures the complete public workload
matrix if correctness passes. The output records the exact tag and commit. Exit
code 2 means the graded implementation did not pass every correctness check.

Terra receives corresponding `init_repository` and `release_candidate` tools. It
must initialize early, publish after correctness milestones, and tag measured
performance improvements. Git runs inside the sandbox. These bounded tools do not
provide an unrestricted shell or access to host credentials. Ineligible benchmark
evidence stays visible but does not establish that a release is faster.

If interrupted during a commit, the preceding completed tag remains the submission.
If no tag exists, there is no graded release. Partial releases can receive partial
correctness credit. Passing the public suite does not establish complete HTTP
conformance. The grader reports both failed and passed cases.

## Export releases and plot progress after a run

```sh
python3 scripts/analyze_releases.py --run RUN_PATH --output .runs/release-analysis
python3 scripts/plot_releases.py .runs/release-analysis
```

The plotting command requires Matplotlib. The analyzer refuses an active run or a
changed evaluator fingerprint. It exports all tags into `implementation.bundle`,
clones a local `implementation/` Git repository, verifies each source hash, then
independently compiles/tests every release. Fully conforming releases receive the
complete performance matrix. These evaluations make no model API calls.

`timeline.json` stores publication timestamps, commits, correctness cases, budget
snapshots, and post-run benchmark rounds. The correctness and performance plots
use elapsed release-publication time on the x-axis. They describe the quality of
the version available at each point during development, measured after the run;
they do not claim those post-run metrics were known by the builder at that time.
In-run measurements are preserved separately under `in-run-benchmarks/`.
Ineligible results use crosses and must not be interpreted as proven improvements.
Each completed evaluation is saved and reused on resumption. Preserve interrupted
partial evaluations and choose a fresh output directory before retrying.
