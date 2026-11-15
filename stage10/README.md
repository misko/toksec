# Stage 10 implementation experiment

Stage 10 uses the regular `toksec` commands and `evaluate.py`, canonical root
[RULES.md](../RULES.md), the shared artifact contract, and the standard result
publisher. This directory implements its specialized TLS sandbox, bounded-request
ledger and partial grader. Builders receive [stage-specific inputs](../stages/stage10/README.md)
and no server source. C++ and Rust workers implement the server and OpenSSL integration.

```sh
python3 -m toksec init --campaign .runs/NAME --budget-usd 2
python3 -m toksec prepare --campaign .runs/NAME --level 10 --language cpp
python3 -m toksec preflight --run RUN_PATH
# The next command makes paid API calls:
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
python3 -m toksec status --campaign .runs/NAME
python3 evaluate.py --section api --run RUN_PATH
python3 evaluate.py --section performance --run RUN_PATH
python3 scripts/publish_results.py --run RUN_PATH
```

Use the run path printed by preparation. Source-only evaluation also supports
`--level 10 --language cpp --source main.cpp`. Successful partial checks return
exit code **4**, not full acceptance. Build/API failures return 2; diagnostic errors
return 1. Performance first requires every implemented partial API check to pass,
then measures HTTP/HTTPS × 256/4096 clients with 4 KiB bodies. All measurements
remain provisional and earn zero final performance credit.

Stage 10 defaults to Terra, medium reasoning, standard service. Each run receives
at most $2 from the enclosing campaign. Preparation does not reserve money; launch
reserves the full allocation in the parent ledger. Known child charges settle that
hold and release unused funds. Uncertain charges retain the full hold and block
further generation. The older `python3 -m stage10.runner` entry point remains for
standalone experiments; campaign-linked runs always use parent accounting even
through that entry point.

Parent grading writes `RUN_PATH/evaluation/<id>/`. Publication uses
`results/stage-10/LANGUAGE/`, with `implementation/`, `inputs/`, `accounting/`, and
parent-owned `evaluation/` kept separate. Historical packets and results stay frozen.

The child ledger covers all model calls within its allocated run cap. Exact provider input counts and bounded
output (including reasoning) are reserved before each generation. Requests admit
at most 32,000 input and 20,000 output tokens: at most $0.23 reserved, with smaller
output requests near exhaustion. Conservative settlement ignores cache discounts.
Uncertain charges block further generation; automatic restart/retry is disabled.
Provider counting, output enforcement and documented pricing remain trusted.
Standard service tier and medium reasoning are mandatory. The wall limit is two
hours. A single process lock and durable SQLite ledger protect a campaign.

Compilation, standalone worker-written tests, Git operations and all candidate
execution are sandboxed. Candidate runtime uses a separate network namespace,
readonly fixtures, one CPU, 512 MiB aggregate cgroup memory (no swap), and 64 MiB
scratch. Two configured workers permit four tasks including the namespace
supervisor, with 4096 descriptors per process. Build resources differ. The host
verifies effective cgroup limits before executing candidate code and kills the
whole cgroup on exit. Private test certificate keys are supplied; API credentials
and host grading source are not mounted in the candidate sandbox.

The output is `repository/`, with monotonically numbered `release/*` tags. Early
bootstrap releases are allowed; subsequent tags must preserve passed visible
checks. Only the last completed tag is exported and independently rebuilt for
`grade`. Candidate attempts, tool responses and the budget ledger remain available
for audit.

**Coverage limitation:** ordinary smoke and an independent partial API checker
are implemented. The full configuration/reload/resource matrix and calibrated
performance grading are not complete. `benchmark_candidate` offers a provisional
256/4096-client HTTP/HTTPS diagnostic with latency, throughput, generator lag and
resource measurements. It is never a final Stage 10 performance grade. Reports
explicitly mark `final_grade_eligible: false`.

Verification:

```
python3 -m unittest discover -s tests -q
TOKSEC_STAGE10_SANDBOX_TEST=1 python3 -m unittest tests.test_stage10_sandbox -v
```
