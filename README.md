# Toksec

Implement and benchmark nginx-like HTTP servers with an AI agent under an enforced
campaign budget. Builders start without server code, test their own implementations,
and publish periodic Git tags. The parent independently grades the last completed
tag and publishes its source, accounting, reports, and figures.

Start with the [CLI walkthrough](docs/cli-walkthrough.md),
[repository map](docs/repository-layout.md), [documentation index](docs/README.md),
and [published results](results/README.md).

## Supported stages

Stages 1–5 and 10 are independent Rust or C++ assignments. Their canonical instructions
live in [stages/](stages/), with shared builder policy in [RULES.md](RULES.md).
Builders receive English requirements and minimal smoke examples; the full API
checker stays on the host. Preparation generates and freezes each run’s packet directly from these sources.
Optional previews go under `.generated/packets/`; historical packets live in
[Git history](https://github.com/misko/toksec/tree/37d353034de935e32e40c31f71a44dbbc473e7b2/archive/task-packets).

| Stage | Target |
|---|---|
| 1 | Static GET, strict framing, path confinement, and deadlines |
| 2 | GET/HEAD, persistent connections, pipelining, and concurrent service |
| 3 | Hosts, routes, indexes, MIME types, validators, and ranges |
| 4 | Reverse proxying, upstream reuse, bodies, and failure handling |
| 5 | Plaintext caching, rate limiting, reload, and graceful drain |
| 10 | Experimental nginx configuration, HTTPS/TLS, streaming, cache coordination, and workers |

[Stage 10 inputs](stages/stage-10/README.md) use the same public runner, evaluator,
shared rules, and result publisher, with documented [Stage 10 execution constraints](docs/stage-10-runtime.md).
Its independent checker remains partial;
its results do not establish full Stage 10 acceptance. Stages 6–9 remain a
[design proposal](docs/stages-6-10-design.md), not runnable profiles.

Stage 1–5 workloads use 4 KiB and 64 KiB bodies at 256 and 4096 clients. Reports
include goodput, latency, failures, timeouts, CPU, memory, and generator saturation.
Read the [historical calibration limitations](docs/stages-3-5-v8.md) before comparing results.
Passing smoke checks is not full API acceptance. Failed parent API correctness
skips performance and earns zero performance credit.

## Evaluate and publish without model calls

The runtime requires Linux, Python 3.11+, the selected Rust/C++ compiler, Bubblewrap,
and nsenter. Benchmarks require separate server/generator CPUs and sufficient file
descriptors. Stage 10 additionally requires OpenSSL development files and delegated
user-systemd cgroups. Compilation and candidate execution are sandboxed.

```sh
python3 evaluate.py --section api --stage 1 --language cpp --source main.cpp
python3 evaluate.py --section performance --run RUN_PATH
python3 scripts/publish_results.py --run RUN_PATH
```

Tagged grading defaults to `RUN_PATH/evaluation/<id>/`. Permanent results live in `results/<run-id>/` and separate
`implementation/` from parent-owned `evaluation/`. The persisted run ID is identical
in raw storage, publication and parent reports. The latest index shows one run per
stage and language without overwriting older results. See the
[artifact workflow](docs/result-storage.md) for reports, figures, and migration.

## Prepare and launch a campaign

Preparation does not call the model:

```sh
python3 -m toksec init --campaign .runs/http-campaign --budget-usd 3
python3 -m toksec prepare --campaign .runs/http-campaign --stage 1 --language cpp --model gpt-6.1-terra
python3 -m toksec preflight --run RUN_PATH
```

Preparation prints `RUN_PATH`. Stage 1–5 CLI defaults are a fresh $3 campaign and
a two-hour run ceiling. Runs prepared in one campaign share its spending balance.
Preflight checks the environment, pinned pricing, freshness, and available budget;
it does not verify account credit or model access.

The following command makes paid API calls. Configure credentials securely:

```sh
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
```

All model requests use standard service. Prompts, feedback, reasoning, and final
reporting count toward the cap. The controller reserves before dispatch, settles
reported usage, and blocks further generation on uncertain charges. Strict
reservations can stop a run before its entire dollar balance is spent. The
[Stage 10 execution path](docs/stage-10-runtime.md) reserves a run allocation from that same
campaign before launch, then uses its bounded-request ledger within the allocation.
Stage 10 defaults to Terra and allows at most $2 per run. Successful partial API
checks and provisional performance diagnostics return exit code 4, never full acceptance.

Builders choose their implementation and testing strategy. They publish working
tags early and continue improving while capacity remains. Untagged edits do not
replace the final submission. No framework can guarantee a working server before
the first successful tagged implementation.

## Verify and preserve evidence

```sh
python3 -m unittest discover -s tests -v
TOKSEC_STAGE10_SANDBOX_TEST=1 python3 -m unittest discover -s tests -v
```

These are framework regression tests, separate from submitted-server acceptance
checks. See [test guidance](tests/README.md) and the [script index](scripts/README.md).

The retired Python pilot is available in [Git history](https://github.com/misko/toksec/tree/37d353034de935e32e40c31f71a44dbbc473e7b2/legacy/python_pilot). [Reference implementations](references/README.md)
had different test access and must remain separate from budgeted experiments.
Historical raw runs, task packets, and published evidence remain frozen. Use the
original recorded checkout to reproduce an old fingerprint; do not rewrite a run's
manifest to make it pass under changed code.
