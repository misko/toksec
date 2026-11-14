# Stage 3–5 alignment: v8

The new protocol lives on `codex/stages-3-5-alignment`. Original v7 worktrees,
records and published contracts are unchanged. Stage 5 is now the explicitly
named bare-bones operations profile: cache, limiter, reload and drain over HTTP.
TLS/gzip remain in historical v7, not an available v8 profile.

## Builder inputs

Every stage starts with no source code. The agent receives RULES.md, its language
interface, the common executable/HTTP/benchmark contracts, its resolved capability
requirements, configuration and ordinary smoke descriptions. Stage 3–5 each have
four supplied checks: GET, HEAD, sequential persistent GETs, plus respectively a
second-host GET, healthy proxied GET or ordinary cache hit.

The agent chooses how to implement, debug, test and optimize. Controller tools
compile and run source in private sandboxes; Git tools create the private repo
and publish tags. Test programs are self-contained: there is no automatically
running candidate server in run_tests. No comprehensive test source, edge fixture,
held-out check ID/count/result or prior implementation is included in the packet.

Builder submission, revalidation, release metadata and checkpoints use smoke
results only. `smoke_passed` replaces the misleading `full_acceptance` field.
The final host grader extracts tagged source and independently tests it. API
failure means no performance measurement and zero performance credit. Existing
plotting still reports independent API passes and eligible metrics at tag times.
There is no invented overall weighted score; progress/marks weights remain open.

## Where things live

- `RULES.md`: common agent freedom, tags, grading and capacity rules.
- `stages/common/`: executable interface, HTTP semantics, benchmark definitions.
- `stages/capabilities/`: persistence, routing, proxy and operations requirements.
- `stages/stageN/{SPEC.md,profile.json,api.py,performance.py}`: stage scope and selection.
- `evaluation/api/`: canonical reusable host checks, including shared static/persistence checks.
- `evaluation/catalog.py`: host case metadata with visibility and contract references.
- `evaluation/smoke/`: ordinary checks and upstream fixtures without fault endpoints.
- `evaluation/performance/fixtures/`: host-only calibration probe, never builder input.
- `toksec/fixtures.py`: independent host edge/fault fixtures.
- `tasks/v8/{rust,cpp}/`: generated packets for all five stages.

C++ and Rust use the same HTTP tests/workloads. Binary dependency inspection
rejects unapproved dynamic libraries and runtime loaders. C++ additionally checks
header provenance. This enforces ordinary builds; it is not a proof against an
adversarial compiler/linker bypass. Both languages retain OS/standard libraries.

## Evaluating and hill climbing

```sh
python3 evaluate.py --section api --level 3 --language cpp --source /path/to/main.cpp
python3 evaluate.py --section performance --level 4 --language cpp --source /path/to/main.cpp
python3 evaluate.py --section performance --run /path/to/completed/run
```

The performance command runs full API acceptance first. API failures return exit
2; ineligible/failing performance returns exit 3. Scored workloads are disclosed.
Stages 3/4/5 have 12/16/24 workloads respectively: inherited static traffic,
routed alias traffic, then proxy and cache-hit/miss traffic as applicable.

The builder can call `benchmark_candidate` with `{"workload": null}` for the
full matrix or `{"workload":"routed-4096-256"}` for a scoped diagnostic.
Subset evidence never promotes a full-matrix comparison baseline. Results record
the selected workload IDs. Five rounds, 256/4096 clients and 4/64 KiB sizes remain.
Proxy/operations benchmarks require six available CPUs: server, four generators,
and upstream. Upstream CPU utilization is recorded; saturation invalidates results.
Cache-hit workloads use a 60-second TTL and warmup; max-age=0 drives cache misses.

## Independent grading recovery

Independent grading checkpoints after API checks and each complete workload.
A resumed analysis verifies source/profile/framework identity and preserves
finished workloads. Interrupted compilation/API checks are archived and rerun;
there are no new model calls.

```sh
python3 scripts/analyze_releases.py --run /path/to/finished/run --output /path/to/run/analysis
python3 scripts/run_series.py --grade-only --run /path/to/finished/run \
  --plot-python /path/to/python-with-matplotlib --status-file /path/to/status.json
```

The series worker writes a separate heartbeat containing PID and update time.
Run a long-lived worker under a process supervisor or detached session; the CLI
itself does not promise survival of its parent terminal. Grade-only refuses an
unfinished builder and requires no API key. Automatic model-call resumption stays
disabled, so an uncertain billable request cannot be silently replayed.

## Calibration and launch readiness

```sh
taskset -c 16-21 python3 scripts/calibrate_benchmarks.py \
  --output .calibration/static-probe --rounds 1
```

The host-only C++ probe tests generator headroom for the Stage 2 static matrix.
It is deliberately not a conforming server and is not graded or given to agents.
Its report distinguishes static readiness from upstream/proxy readiness. A static
probe cannot certify proxy attribution. Keep eligibility thresholds unchanged.

Initial calibration found generator saturation across the eight static workloads.
Therefore no new paid higher-stage campaign has been launched. Fix or replace the
load generator and demonstrate headroom, then validate a conforming proxy reference
with dedicated upstream resources before making performance comparisons.

Preparation and local validation spend no model budget. Future authorized runs
can retain Terra medium/default tier, independent $3 campaign caps and two-hour
builder ceilings. Strict reservation still permits early admission stopping; it
is not evidence that performance has been maximized.

## Validation recorded for this change

`python3 -m unittest discover -s tests -v`: **89 tests passed**. This includes
real sandboxed Rust/C++ compilation, real higher-stage smoke traffic and ordinary
upstream processes, source/dependency restrictions, held-out feedback isolation,
Git tags/checkpoints, final-tag API gating, and interrupted-grading recovery.
The proxy benchmark integration verifies disjoint server/generator/upstream CPUs.

The final static calibration used separate CPUs from the regression suite and
found seven of eight workloads ineligible due to generator saturation. One valid
single round is not a five-round performance comparison. See the saved
[calibration results](../results/2026-11-14-v8-calibration/README.md).

A fully conforming Stage 3–5 reference implementation has not been validated
against every host case. Existing cases were preserved (except the explicitly
removed TLS/gzip profile), with added routing/proxy interaction coverage and a
stronger in-flight drain check. Full reference validation, broader edge coverage
and generator/upstream calibration remain follow-up work before treating this
as a mature performance benchmark. No new paid builder calls were made.
