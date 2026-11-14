# Shared rules and stage suites

```text
RULES.md                       # grading, tags, freedom, budget and stopping
stages/
  common/
    INTERFACE.md               # main.rs, build, launch, config and resources
    HTTP.md                    # common parsing, framing and static-file behavior
    BENCHMARK.md               # load protocol, metrics and validity
    api.py                     # shared file-serving checks
    performance.py             # workload type and common matrix builder
  stage1/
    SPEC.md                    # GET, close after response, header deadline
    api.py                     # Stage 1 check registry
    performance.py             # fresh-connection matrix
  stage2/
    SPEC.md                    # HEAD, persistence, concurrency and backpressure
    api.py                     # shared checks plus Stage 2 checks
    performance.py             # fresh and persistent matrices
```

Stage 2 imports common checks, never Stage 1's implementation or stage contract.
Neither receives a starter. The process interface and configuration format are
identical, while the stage contract determines connection behavior.

| Area | Stage 1 | Stage 2 |
|---|---|---|
| Methods | GET | GET and HEAD |
| Connections | Close after each response | HTTP/1.1 persistence, ordered pipelines |
| Concurrency | Optional implementation strategy | Independent service despite slow clients |
| Limits | Bounded headers and absolute read deadline | Also connection count, idle/write deadlines, request count and pipeline backpressure |
| Independent API cases | 12 | 21 |
| Performance workloads | 4 fresh | 4 fresh plus 4 persistent |

Every workload uses 256 or 4096 clients and 4 KiB or 64 KiB responses. Shared
measurement machinery lives in toksec/benchmark.py; each stage owns its workload
selection. Do not duplicate the load generator just to separate stage definitions.

The runner assembles RULES, interface, common HTTP semantics, the selected SPEC,
and benchmark guidance into launch-packet.md. It snapshots the source documents
under builder-inputs and records the exact machine-readable specification.
English requirements, check descriptions and workloads go into model context;
independent checker Python source stays on the host. Tool calls return evidence.

API failure skips performance execution and records zero performance credit.
Partial correctness and milestone evidence remain visible. There is no invented
numeric total score: milestone weights and the throughput-to-marks formula are
still undefined. Tests for backpressure demonstrate external behavior, not a
proof of internal memory bounds.

The CLI defaults to a fresh $3 campaign and two hours per prepared run. Multiple
runs in one campaign share $3; they do not each receive $3. Strict reservation can
stop them early. No paid experiment is started by preparing these files.

Regenerate published packets with:

```sh
python3 -m toksec publish --output tasks/v5
./evaluate.py --section api --level 1 --source /path/to/main.rs
./evaluate.py --section performance --level 2 --source /path/to/main.rs
```

Older tasks and running experiments retain their original evaluator fingerprint.
Use their original checkout to grade them.
