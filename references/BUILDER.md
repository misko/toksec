# Reference builder instructions

Implement the assigned stage and language completely. Read its resolved contract,
the shared interface and language policy, and all applicable full host tests.
Honor the English contract, including requirements not exhaustively tested.
This is a trusted reference task: full evaluator inspection is allowed.

Work only in your assigned reference directory and unique evaluation output
directories. Do not modify contracts, evaluators, other references, experimental
sources, run records, or accepted artifacts. Report suspected grader defects to
the coordinating agent with a minimal reproducer and the relevant contract text.
Do not special-case fixture names, paths, request values, or evaluator behavior.
Do not start paid model calls. Native agent workspaces are shared filesystem
workspaces; compiled candidates are executed through the sandboxed evaluator.

Deliver one main.rs or main.cpp conforming to the existing compile and executable
interface. No dependencies beyond the approved standard library and OS primitives.
Implement from scratch; do not copy earlier experimental server implementations.
Keep each target independently compilable. Never pass reference source to an
experimental builder.

Prioritize complete API correctness, then efficient execution. Aim for bounded
per-connection memory, nonblocking or otherwise scalable I/O, slow-client isolation,
accurate deadlines, and efficient file transfers where appropriate. Select the
architecture yourself. Do not claim performance solely from architectural choices.
Maintain a working checkpoint before risky changes. Preserve source snapshots with
hashes when comparing optimization candidates.

Run the full API CLI given in TASK.md and inspect every failure. Add your own
focused tests or diagnostics for gaps in the English contract. Run live server
checks through `sandbox.running` or `references/run_diagnostic.py`, including
the diagnostic driver and its child servers. Do not launch candidates directly
on the host. Iterate until all
required checks pass. If blocked, report the exact requirement and evidence rather
than weakening the implementation or grader.

Coordinate performance runs with the parent: do not run concurrent benchmarks or
compete with another campaign for its assigned CPUs. Once correctness passes,
measure the full declared matrix using the existing evaluator. Treat saturated
load generators/upstreams as inconclusive. Never loosen validity thresholds to
claim success. Keep raw result JSON and compare eligible measurements before and
after optimizations. Report throughput, p50/p95/p99 latency, errors/timeouts, CPU,
RSS, round spread, and measurement eligibility for both client counts.

Write REPORT.md with architecture, unsafe/FFI use where applicable, complete API
result paths, source hashes, performance evidence and any unresolved limitations.
Clearly distinguish implemented, API-validated and performance-validated status.
Do not claim all requirements or performance goals met without supporting evidence.
