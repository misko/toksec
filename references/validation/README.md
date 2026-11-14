# Reference validation campaign

Ten independent native Sol xhigh subagents implemented Stages 1–5 in C++ and
Rust. No model API calls were used. Builders could inspect the full host tests;
these are trusted engineering references, not comparable budgeted experiments.
Native agent workspaces share a filesystem. The full API and performance
candidates execute through the sandboxed evaluator.

## Correctness

All ten frozen sources passed their complete host API suite: **250/250 checks**.
The source hashes, framework fingerprint and result locations are recorded in
[../manifest.json](../manifest.json). Each target's `api.json` is retained here.
Builder reports describe extra contract probes and limitations; finite suites do
not prove exhaustive correctness. Two standalone probes were additionally rerun
through `run_diagnostic.py` and their sandbox evidence is archived here.

## Performance interpretation

The central sweep uses the v2 supplemental native tool: one second warmup, three
seconds measurement, two-second request deadline, one outstanding request per
client, 256/4096 clients, 4/64 KiB bodies, all workloads declared for each stage.
The server has one CPU and a 512 MiB address-space limit. Four generator processes
use separate CPUs; proxy stages use a sixth CPU for the trusted upstream fixture.

These are **one-round supplemental diagnostics**, not canonical five-round scores
or evidence of a measured optimization speedup. CPUs were pinned, but this shared
host had substantial unrelated load and CPUs were not exclusively reserved.
Only eligible, error-free rounds support the limited reported measurement.
Ineligible throughput must not be used to rank implementations. Generator lag,
upstream saturation and request failures remain visible in the evidence.

Version 1 diagnostic eligibility is provisional because its monitor could miss
a scheduling pause crossing the measurement end. The v2 monitor accounts for all
300 scheduled measurement deadlines and retains the original gate as an
additional check. Only v2 evidence is included in the central result table.
The unchanged official Stage 1 C++ five-round matrix also ran; all 20 rounds were
ineligible due to generator saturation. It is documented in that target's report.

## Final-source results

Every source passed its full API gate before measurement. Each supplemental
workload below ran once; eligibility includes generator validity and zero errors.
The counts are workload counts, not performance grades.

| Target | API checks passed | Workloads completed | Eligible | Measured failures | Warmup failures |
|---|---:|---:|---:|---:|---:|
| stage-01-cpp | 12/12 | 4/4 | 2 | 0 | 0 |
| stage-01-rust | 12/12 | 4/4 | 1 | 0 | 0 |
| stage-02-cpp | 21/21 | 8/8 | 5 | 0 | 0 |
| stage-02-rust | 21/21 | 8/8 | 6 | 0 | 0 |
| stage-03-cpp | 26/26 | 12/12 | 10 | 0 | 0 |
| stage-03-rust | 26/26 | 12/12 | 10 | 0 | 0 |
| stage-04-cpp | 31/31 | 16/16 | 14 | 0 | 0 |
| stage-04-rust | 31/31 | 16/16 | 8 | 54 | 61 |
| stage-05-cpp | 35/35 | 24/24 | 17 | 4037 | 0 |
| stage-05-rust | 35/35 | 24/24 | 20 | 641 | 3967 |

Across the final-source full matrices: **250 API checks passed, 128 workloads
completed, 93 eligible single rounds**. [metrics.csv](metrics.csv) contains per-workload
throughput, p50/p95/p99, failures/timeouts, CPU/RSS and eligibility reasons.
Each target's `supplemental.json` retains worker-level diagnostics and source/tool
identities; do not rank targets using ineligible rows.

A separate final-source Stage 4 C++ five-round proxy check is archived in
[stage-04-cpp/proxy-five-rounds.json](stage-04-cpp/proxy-five-rounds.json).
The 4 KiB/256 and 64 KiB/4096 groups were eligible, with median throughput
33,778 and 7,092 requests/s respectively. The 4 KiB/4096 group recorded **5,427
timeouts** despite the error-free single full-matrix sweep. The 64 KiB/256 group
had no request failures but was ineligible. **Stage 4 C++ stability is unresolved.**

Other final-source failures: Stage 4 Rust returned 54 invalid-status responses in
one proxy/256 round; Stage 5 C++ recorded 4,037 timeouts in its 64 KiB cache-miss/4096
round; Stage 5 Rust recorded 641 failures across two proxy/cache-miss rounds.
The native tool's generic status counter does not retain the exact status line.
These are retained failures, not performance passes. No aggregate success or
full-matrix performance certification is claimed for any implementation.

## Changes driven by measurement

Rust Stages 3–5 now explicitly size the listener backlog; kernel probes showed
128 becoming 4096 on this host. Stage 3 Rust's final full sweep had zero request
failures versus 8,019 before the correction. Stages 4/5 added or repaired bounded
upstream admission, FIFO fairness including retries, canceled-request cleanup,
and descriptor generation/authority checks where applicable. Deterministic
regressions reproduced the identified queue and pool bugs before fixes and
passed afterward. All final full API suites passed again.

Initial snapshots are retained as `supplemental-before.json` where sources
changed; intermediate results, including failures, are retained in [history/](history).
They have different source identities and must not be represented as results for
the final source. Individual reports identify the focused regression evidence.

## Remaining performance uncertainty

Repeated high-concurrency proxy failures remain unexplained after the confirmed
source defects were repaired. Bounded functional checks and full API success do
not negate these failures. Load-tool review found no concrete accounting/timing
fault, but the tool monitors generator lag only: CPU totals for server/upstream
do not prove continuous availability or rule out scheduling pauses on CPUs 10/15.
The host load was substantial. Neither a server bug nor host contention has been
established as the cause of the remaining episodes.

Before using these as performance baselines, repeat the canonical five-round
matrix on reserved idle CPUs with a calibrated generator/upstream, retain exact
HTTP failure status and connect-versus-response timeout phases, and collect
server/upstream scheduling-wait traces. This is a validation follow-up, not a
reason to discard or relabel the current failed rounds.

## Reproduction and limitations

Use `references/validate.py` for the canonical API/performance evaluator and
`references/tools/supplemental.py` for the separate native diagnostic; see their
READMEs. Fresh evaluation produces the accepted binary needed by the diagnostic.
Retained raw `.runs/` paths refer to this workspace and are not portable binaries.
A clean checkout can rebuild all sources and rerun the suites. Histograms and
binaries stay in ignored raw output; compact JSON preserves all other diagnostic
fields and the raw result hash. Source files and canonical evaluators are separate
from experimental sandbox inputs and curated experimental `results/`.

Rust Stage 4 supports numeric upstream addresses, not DNS names. Rust Stages 4/5
bound individual proxy bodies but do not have a global body-memory admission
budget: many simultaneous maximum-size bodies may exhaust the process limit.
See individual reports for further architecture and resource limitations. These
references implement the specified stage contracts, not full production nginx.
