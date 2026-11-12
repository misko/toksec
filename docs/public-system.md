# Walkthrough of the public Rust system

The experiment asks how much measured agent capacity produces a working implementation of a fixed interface, and later how much attacker capacity finds an exploit in that implementation. This change implements the builder side. It does not launch another paid experiment or implement the exploit campaign.

## 1. Freeze the target before the agent starts

Use “level” and “stage” to mean the same five complexity targets. Level 2 does not consume a Level 1 implementation. Both receive complete requirements and start from empty source. The specification generator expands shared definitions into standalone packets. Each includes process invocation, configuration keys, HTTP semantics, errors, limits, public check IDs, benchmarks and implementation suggestions.

The process API is `server --config FILE`. Source is one `main.rs`, built with `rustc --edition=2021 -C opt-level=3`. Rust std and direct libc OS primitives are allowed. Level 5 additionally allows system OpenSSL and zlib FFI. HTTP libraries, subprocess servers, Cargo build scripts and downloads are excluded by the task policy. Namespace isolation is enforced; the dependency policy is a research constraint and still warrants source review, not a claim that arbitrary FFI can be statically classified perfectly.

Level 1 closes after each GET. Level 2 replaces that rule with HEAD, persistence, pipelining and independent concurrent service. Level 3 adds routing and representation semantics. Level 4 adds proxying. Level 5 adds TLS and operational features. These are capability descriptions, not implementation dependencies.

## 2. Give the public suite up front

`prepare` writes the expanded prompt, machine-readable specification and a `public-suite/toksec/` package. The runner includes that suite's source in the initial model input. There are no hidden acceptance cases. The candidate cannot alter the suite at execution time. Luna can submit additional Rust unit tests through `run_tests`.

The executable suite tests ordinary behavior, malformed inputs, confinement, deadlines and feature-specific failure handling. It is a finite operational definition of acceptance. Passing every check does not prove universal HTTP compliance, absence of test overfitting or absence of vulnerabilities. The deliberately restricted profile is authoritative where it differs from a general-purpose HTTP server.

The public source is implemented in `toksec/checks.py`, `wire.py`, `fixtures.py`, `sandbox.py`, `driver.py` and `benchmark.py`. `configuration_check` is part of the suite and runs separate processes with invalid configurations. `bootstrap` tests a normal file, an empty file and a missing-file response. The bootstrap is a real artifact criterion, not a compile-only milestone.

## 3. Compile and run in sandboxes

Compilation itself executes tooling against untrusted source, so the compiler also runs in Bubblewrap. It receives read-only source, a read-only pinned toolchain and a dedicated output directory. The build has 4 GiB address space, 60 CPU seconds and 120 wall seconds. No credentials, home directory or external network are provided.

The generated server gets a fresh mount, PID, user and network namespace, read-only fixtures and read-only candidate files. Its address-space limit is 512 MiB, descriptor limit 16384 and CPU affinity one core. A trusted driver joins only its user and network namespaces, keeping evaluator files outside the candidate filesystem. TLS keys are disposable public-test fixture keys.

These are Linux namespace and per-process resource controls, not a VM or cgroup aggregate memory guarantee. Multiprocess server designs are outside the profile. Benchmarks report observed child processes and exclude such results from promotion. A hardened hostile-builder research deployment should add a disposable VM or delegated cgroup for aggregate process and memory limits. This implementation does not claim resistance to kernel exploits or fork-based aggregate resource exhaustion.

The fixed host toolchain version, CPU affinity, platform, initial load and source fingerprint are recorded. Runtime library versions remain properties of the host installation. Use a pinned host image when comparing separate machines or dates.

## 4. Retain progress before optimizing

The controller archives every submission. A compilation failure leaves the accepted pointer unchanged. A partially conformant candidate must pass bootstrap, preserve every previously passed check and add at least one. The first fully accepted implementation becomes the incumbent.

Subsequent candidates must pass the entire suite. A complete benchmark compares incumbent and challenger in alternating order, five rounds per workload. Promotion requires all of the following.

- No request failures on either side.
- No load-generator saturation or observed child processes.
- No p99 regression above 5% in any workload.
- Challenger minimum goodput above incumbent maximum goodput in every workload.
- At least 5% improvement in geometric-mean goodput across workloads.

This deliberately conservative rule may reject useful tradeoffs. It preserves an incumbent when the evidence is noisy. The controller does not claim that the retained implementation has globally maximal performance. Equal functional coverage among partial implementations also keeps the incumbent.

`finish` asks for a report. While capacity remains it requires full acceptance and an evaluated optimization attempt. It permits stopping when time cannot accommodate a full comparison. A deadline can interrupt a compile or benchmark; cleanup runs and the prior accepted pointer remains usable. Before the first bootstrap pass, the honest result can still be “no working artifact.” Providing a hand-written fallback would change the from-scratch experiment.

## 5. Measure service at both concurrency settings

Each workload uses 256 or 4096 client loops with one outstanding request per loop, distributed over four generator processes on CPUs separate from the server. It is closed-loop load. A “client” includes a client attempting a connection; failed connections and timeouts are part of the result. The result does not imply that every client had an established socket simultaneously.

Local files are 4 KiB and 64 KiB. Applicable modes are fresh connections, persistent connections, proxy, TLS and gzip. Each round warms for one second and measures for three seconds. Requests have two-second deadlines. Five rounds are saved, not just their aggregate.

Goodput counts correct responses completed inside the measurement window. Payload throughput counts their decoded application bytes. Latency includes connection setup or TLS handshake when needed. Successful requests started inside the window contribute latency even if they finish during the bounded drain. Failures and timeouts are separately counted. A failed request is not silently retried within its measurement; the client can begin its next distinct request afterward.

Latency histograms have 100-microsecond bins. Reports include p50, p95 and p99, median/min/max goodput, CPU, sampled peak RSS, generator lag and process counts. More than 90% generator CPU utilization, or excessive event-loop delay, marks measurements inconclusive for promotion. These diagnostics can detect common generator limits but do not prove the generator is never a bottleneck. Shared-host interference remains visible through spread and load metadata. Successful-request percentiles must always be read alongside failure counts.

Functional acceptance and load service quality are separate fields. A server can pass the API checks and still time out at 4096 clients. The framework reports that outcome without declaring those timeouts successful service.

## 6. Account for one campaign

One durable ledger covers all independently prepared runs. It imports the recorded pilot once when the campaign directory is created. Keep using that directory. A lock serializes model runners; a second lock protects atomic reservations and settlement. A pending request prevents further inference. Unknown usage is never silently forgiven or retried.

The dollar cap is $5 across measured API prompts through final model reporting. The additional token ceiling is 10 million input-plus-output tokens. Cached inputs and reasoning are reported as subsets, not added twice. The token ceiling is a conservative guard under the supported context regime, not a universal conversion between dollars and tokens.

The pinned standard pricing and model context ceiling are documented by [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-luna). The runner reserves 1,066,000 tokens and $0.537 before each inference call to cover the model-wide input ceiling plus 16,000 output tokens under conservative cache-write and long-context rates. It settles reported usage afterward. This is intentionally much more conservative than the prompt-size estimate because the prior pilot's counting endpoint underestimated actual input. Requests above 64,000 counted input tokens are refused; unexpectedly larger actual input is settled and stops the campaign. Pricing older than seven days blocks a new launch pending review.

A reservation is capacity held aside, not money claimed spent. At low balance, the runner may stop with unused dollars. API charges, token usage, wall time and local compilation/benchmark resources are separate quantities. Unmetered framework work in this chat is excluded and cannot be reconstructed as part of a $5 all-inclusive research cost.

`budget_status` returns remaining dollars, used/reserved/remaining tokens, the next-call reservation, wall time, retained candidate and acceptance state. The runner also inserts a snapshot before every model request. The API key stays in the trusted controller. Standard processing is explicit. No native Codex subagent is used as a substitute for a metered API run.

## 7. Run and inspect

From the repository root, initialize one campaign and prepare a level using the README commands. Preparation makes no API requests. Review its generated packet and run local preflight. `run` is the explicit paid launch command. Prepare each subsequent level against the same campaign path.

For local harness development, `submit --run RUN --source main.rs`, `test --run RUN --source tests.rs` and `benchmark --run RUN` use the same sandbox interfaces. A measured Luna run refuses a workspace that already contains manual candidates, preventing a supplied implementation from quietly entering a from-scratch build.

Inspect `result.json`, each candidate's `report.json`, optional `benchmark.json`, raw response records, tool results and the campaign ledger. `benchmark-progress.json` preserves completed rounds if a later round fails. The final result always points to the retained snapshot rather than the last edited source. Failed or partial results identify unmet public checks.

## 8. Hand off to the future exploit side

Freeze the accepted source hash, binary, build recipe, exact API/suite version, resource environment and build-cost ledger. Give the attacker an independently metered budget. Report exploit cost conditional on functional acceptance and workload coverage. A cheap exploit against a nonworking server should not be compared with an exploit against a fully accepted server without that distinction.

The current implementation prepares this artifact handoff. It does not yet execute, validate or cost attacker campaigns.
