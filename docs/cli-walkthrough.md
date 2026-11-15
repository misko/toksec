# Evaluate, run, and publish

Run these commands from the repository root. Stages 1–5 and 10 support Rust and C++
through these same commands. Stage 10 retains [partial independent coverage and
provisional performance](stage-10-runtime.md). No current builder receives starter code.

## Check a source file without model calls

```sh
python3 evaluate.py --section api --stage 1 --language rust --source main.rs
python3 evaluate.py --section performance --stage 2 --language cpp --source main.cpp
```

The API section compiles in a sandbox and runs the selected independent API suite.
The performance section first runs that same API gate. Any failed build or required
API check skips performance and earns zero performance credit. An unmeasured
throughput or latency is not a measured zero.

Without `--output`, standalone source checks write `evaluation-results/<id>/`.
With `--run`, grading extracts the last completed tag and writes
`RUN_PATH/evaluation/<id>/`. Untagged working-tree edits do not change the submission.
Old runs require their recorded evaluator checkout and fingerprint.

Exit codes are 0 for success, 1 for evaluator errors, 2 for build/API failure, and
3 for missing, ineligible, or failing full-stage performance measurements, and
4 for successful Stage 10 partial checks/provisional diagnostics. Stage 10 diagnostics
cover HTTP and HTTPS with 4 KiB bodies at 256 and 4096 clients; they earn zero final
performance credit even when every implemented API check passes. Read failures and
load-generator saturation alongside latency and throughput.

## Prepare an independent campaign

These commands do not call the model. Commit framework changes first; preparation
requires a clean Git checkout and records its full commit SHA:

```sh
python3 -m toksec init --campaign .runs/terra-example --budget-usd 3
python3 -m toksec prepare --campaign .runs/terra-example --stage 1 --language cpp --model gpt-6.1-terra --wall-seconds 7200
python3 -m toksec preflight --run RUN_PATH
```

Use the run path printed by preparation. Multiple runs prepared in one campaign
share its ledger. Each run starts independently with no implementation code.
The default campaign cap is $3 and the default run ceiling is two hours. Strict
request reservations can stop admission before all dollars are spent.

Stage 10 uses the same preparation command with `--stage 10`. It defaults to
`gpt-6.1-terra` (the only supported Stage 10 model), medium reasoning, and a maximum
$2 run allocation from the shared campaign. `--spend-target-usd` is a hard allocation
cap for Stage 10; for Stages 1–5 it remains a soft stopping target. Preparation
spends and reserves nothing. At launch the parent reserves the whole Stage 10
allocation, then settles known usage and releases the unused balance on completion.
Uncertain usage keeps the reservation and blocks further dispatch.

```sh
python3 -m toksec init --campaign .runs/tls-example --budget-usd 2
python3 -m toksec prepare --campaign .runs/tls-example --stage 10 --language cpp
python3 evaluate.py --section api --stage 10 --language cpp --source main.cpp
```

The following command makes paid model API calls:

```sh
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
```

All requests use standard service. Uncertain charges block further dispatch.
Preparation and test execution CPU are outside the model-spend accounting scope.
These instructions do not authorize additional paid runs.

## Builder feedback and final grading

The builder receives English requirements, configuration, language/resource rules,
a generated artifact contract, minimal smoke descriptions, and workload parameters.
It chooses its own architecture, tests, and optimization strategy.

`submit_candidate` and `revalidate_candidate` run visible smoke checks, not the full
parent API suite. `benchmark_candidate` provides provisional development measurements
after smoke acceptance. `run_tests` runs builder-written standalone test programs.
`init_repository` and `release_candidate` publish working numbered Git tags through
the controller. Only the last completed tag is the final submission.

After the run, independently grade and publish that tag:

```sh
python3 evaluate.py --section performance --run RUN_PATH
python3 scripts/publish_results.py --run RUN_PATH
```

The parent creates the evaluation record and report. Put figures derived from the
same evaluation in its `figures/` directory before publication. The publisher writes `results/<run-id>/`, preserving the raw run’s persisted ID.
It separates implementation, inputs, accounting, and parent evidence. The latest
index selects by start time, so publishing an older experiment cannot replace a
newer entry in the current view. See
[result storage](result-storage.md) for the exact layout and provenance rules.

`scripts/analyze_releases.py` and `scripts/plot_releases.py` retain the older
Stage 1–5 all-tags timeline workflow. Stage 10 currently uses the shared last-tag
grading and publication commands above. Their explicit analysis outputs remain supported by
the publisher; they are not builder feedback or permission to regrade a frozen run
with another evaluator. See the [script index](../scripts/README.md).

## Stage names and provenance

Use `--stage 1`; `--level 1` remains a compatibility alias. Stage directory names
are `stage-01`, `stage-02`, and `stage-10`. New manifests write integer `stage`.
Runs record `toksec_commit` at preparation. Evaluations record their own
`toksec_commit` and `toksec_dirty`, plus `run_toksec_commit` for tagged grading.
The evaluator commit and the submitted server's `release.commit` are different.
Historical records without commit provenance remain explicitly historical.
