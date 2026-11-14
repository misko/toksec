# Trusted HTTP reference implementations

Ten independent targets: Stages 1–5, each in Rust and C++.
All ten pass the full API suites (250 checks). Performance validation is partial:
final-source stress failures remain in Stages 4/5; see the validation report.
These are engineering references, not budgeted experimental builder results.
Reference builders may inspect the full host tests. Reference source must never
be included in experimental sandbox inputs.

Sources live in `stage-NN/LANGUAGE/main.rs` or `main.cpp`; each target has a
`TASK.md` and a `REPORT.md` recording validation and limitations.
Shared builder instructions live in `BUILDER.md`. Resolved requirements remain
in `tasks/v8/LANGUAGE/level-N.md`; this directory does not redefine the protocol.

Keep evaluation artifacts under `.runs/references/`, separate from the curated
experimental `results/` tree. Record source SHA-256 and framework fingerprint
with every result. API acceptance is mandatory before performance measurement.
A reference is not validated until its full API suite passes. Passing those tests
alone is not proof of completeness; builders must also review the English contract.

Performance requires eligible, error-free measurements with latency, throughput,
resource usage and generator validity reported at 256 and 4096 clients. Generator
or upstream saturation is inconclusive, not evidence of server performance.

Run all ten full API evaluations serially, or select individual targets:

```sh
python3 references/validate.py --section api --cpus 10,11
python3 references/validate.py --stage 1 --language cpp --section performance --cpus 10,11,12,13,14,15
```

Choose available, otherwise idle CPUs for the host. The script checks source
availability before starting, requires enough CPUs for the selected stages,
serializes its own invocations with a lock, and retains each result plus a summary
under `.runs/references/validation/`. It does not coordinate external processes;
reserve CPUs before invoking it. A performance run repeats the full API gate.
Exit status is nonzero if any source fails correctness or any performance result
is ineligible or has failed requests. Never treat a partially completed run as
full validation. Stop editing a reference before evaluating its final snapshot.

| Stage | Capability added | Full API checks | Performance workloads per language |
|---|---|---:|---:|
| 1 | Static GET files, strict parsing and path confinement | 12 | 4 |
| 2 | HEAD, persistence, pipelining and connection deadlines | 21 | 8 |
| 3 | Hosts, routes, indexes, ETags and byte ranges | 26 | 12 |
| 4 | Reverse proxy, body framing and upstream reuse | 31 | 16 |
| 5 | Cache, rate limiting, reload and graceful drain | 35 | 24 |

Run a standalone Python diagnostic and all of its server children inside a
sandbox with a read-only repository and one writable result directory:

```sh
python3 references/run_diagnostic.py \
  --output .runs/references/stage-01-cpp/focused-NEW -- \
  references/stage-01/cpp/focused_tests.py \
  .runs/references/stage-01-cpp/api-002/candidate/server \
  .runs/references/stage-01-cpp/focused-NEW/checks
```

The diagnostic may also use the sandbox's temporary directory for short-lived
fixtures. The wrapper limits memory, CPU time, descriptors and wall time and
retains stdout, stderr and invocation metadata. Scripts already using the
sandbox evaluator should use their documented entry point instead.

The source identities and accepted API evidence are indexed in
[manifest.json](manifest.json). See [validation/README.md](validation/README.md)
for the campaign outcome and [tools/README.md](tools/README.md) for the separate
supplemental native load diagnostic. Reference agents were native subagents;
this workflow made no model API calls.
