# Public Rust campaign system

## Definition of done

Five independent level packages expose a complete process/configuration/wire API, executable public checks, and declared workloads at 256 and 4096 active clients. A controller compiles and executes Rust only in sandboxes, retains immutable working candidates, and admits all model requests through one $5 campaign ledger including the recorded pilot. No paid run is part of framework preparation.

## Workflow and decisions

1. Ground the Python pilot and resource limits. Complete. The current host has Rust, OpenSSL and Bubblewrap; the soft descriptor limit is too low for 4096 clients.
2. Freeze the data shapes and all five public contracts. Implement specifications before runner integration.
3. Implement sandboxed compilation and runtime; verify isolation with real compiled fixtures.
4. Implement public protocol checks and concurrent workload metrics; verify failure detection and both requested concurrency settings.
5. Integrate independent runs, candidate promotion, optimization feedback, and the shared ledger.
6. Verify the CLI and integration tests, publish a reviewable change, and walk through the workflow.

The core records are LevelSpec, Candidate, and CampaignLedger. One controller owns each ledger. Each run gets an empty source workspace and only its own prior candidate. Levels share specification definitions but never implementation artifacts or model context.

Alternatives considered: extending every Python-pilot branch versus a versioned Rust package. The versioned package preserves the published pilot and gives compiled artifacts their own build/runtime lifecycle. A benchmark can report correctness and latency without a universal scalar score; promotion requires no lost public checks and a reproducible improvement in the declared workload vector.

Throughput checkpoint: first verify compilation isolation and high-concurrency resource support. Specification, runtime, suite, and accounting modules have distinct ownership, but a single worker integrates their shared interfaces. Native delegation is omitted because this host's exposed launcher has no service-tier selector; independent agent review is not claimed. Repository tests and CLI checks substitute for unavailable cursor-team-kit tooling.

The latest user instruction supersedes the prior suggestion-only acceptance policy. All acceptance checks are public and supplied up front. Luna may add tests. There is no hidden final suite.

The $5 ledger covers measured Luna prompts through final reporting, including the old pilot. Preparation in this chat was not metered by the runner and cannot be retroactively included. Local compilation and benchmark compute are separately recorded, not API charges.

## Completed checkpoints

All six workflow steps are complete for framework preparation. The implementation includes generated level packets, a self-contained public suite, Rust compile/runtime sandboxes, candidate retention, paired benchmark selection, a shared campaign ledger, a metered tool loop and CLI commands. Five empty runs are prepared locally. No new paid run was launched.

Model the Domain shaped the explicit specification, workload, candidate and ledger records. Prove It Works required real sandboxed compilation, socket traffic, credential-isolation checks and both concurrency settings. Explain the Number kept successful-request latency separate from failures and marked generator saturation as inconclusive. Sequence Work into Verifiable Units separated compiler checks, accounting/tool-loop checks and full integration verification.

The implementation and remaining validation limits are recorded in system-verification.md. The decision trail is in system-decisions.tsv.
