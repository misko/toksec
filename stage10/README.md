# Stage 10 implementation experiment

This isolated runner extends the draft Stage 10 packet without changing the frozen
Stage 1–5 framework. It supplies no server source. The worker implements the HTTP
server and its OpenSSL integration in C++ (default) or Rust.

```
python3 -m stage10.runner prepare --run .runs/NAME --language cpp --budget-usd 2.00
python3 -m stage10.runner run --run .runs/NAME --key-file ~/.codexapi
python3 -m stage10.runner status --run .runs/NAME
python3 -m stage10.runner grade --run .runs/NAME
```

The $2 ledger covers the entire campaign. Exact provider input counts and bounded
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
