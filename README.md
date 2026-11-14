# Toksec

Implement and benchmark nginx-like HTTP servers with an AI agent under a measured campaign budget.

Stages 1 through 5 are independent, from-scratch Rust or C++ tasks: none receives starter code or another implementation. The agent receives shared English rules, its stage contract, configuration, minimal smoke-check descriptions and workload matrix. Independent checker implementations stay on the host. Stages share one campaign ledger.

See [v8 alignment and calibration status](docs/stages-3-5-v8.md) for the new Stage 3–5 protocol and remaining benchmark bottleneck.

The authoritative instructions live in [RULES.md](RULES.md). See [the stage layout](docs/stage-layout.md) for shared and stage-specific files. Published packets are generated snapshots; edit the source documents and regenerate them.

| Level | Complete target | Performance workloads |
|---|---|---|
| [1](tasks/v8/rust/level-1.md) | GET static files, strict framing, confinement and deadlines | Fresh HTTP |
| [2](tasks/v8/rust/level-2.md) | Static GET/HEAD, persistent connections, pipelining and concurrent service | Fresh and persistent HTTP |
| [3](tasks/v8/rust/level-3.md) | Hosts, routes, indexes, MIME types, ETags and ranges | Fresh and persistent HTTP |
| [4](tasks/v8/rust/level-4.md) | Static/routing API plus reverse proxy, upstream reuse, request bodies and failure handling | HTTP plus proxy |
| [5](tasks/v8/rust/level-5.md) | Previous capabilities plus cache, rate limiting, reload and graceful drain | HTTP, routed files, proxy, cache hits and misses |

Every mode runs with 4 KiB and 64 KiB bodies at **256 and 4096 active clients**. Five rounds report goodput, p50/p95/p99 latency, failures, timeouts, CPU, RSS and load-generator saturation. This is a defined nginx-inspired subset, not a quantitative claim of half of nginx.

See [the CLI walkthrough](docs/cli-walkthrough.md) for standalone checks, performance measurements, from-scratch campaigns, and hill-climbing reports.

Evaluate source with `./evaluate.py --section api --level 1 --source main.rs` or
`./evaluate.py --section performance --level 1 --source main.rs`. Grade the last
completed sandbox Git tag with `./evaluate.py --section performance --run RUN_PATH`.
The builder is instructed to publish working releases throughout the run; untagged
edits do not replace the graded submission.

## Prepare without spending

Requires Linux, Python 3.11+, Rust, GCC, Bubblewrap, nsenter, five available CPUs (six for proxy/operations benchmarks) and a descriptor hard limit of at least 16384. Compilation and generated execution both use private namespaces. Host credentials are not mounted.

```sh
python3 -m toksec publish --output tasks/v8/rust
python3 -m toksec init --campaign .runs/http-campaign
python3 -m toksec prepare --campaign .runs/http-campaign --level 1
python3 -m toksec prepare --campaign .runs/http-campaign --level 2
python3 -m toksec status --campaign .runs/http-campaign
```

Prepare prints a unique run path. The CLI defaults to a fresh **$3 campaign** and a **two-hour run ceiling**. Use one campaign directory for a shared cap; two prepared runs share its balance. A different campaign directory starts a separate accounting scope.

```sh
python3 -m toksec preflight --run RUN_PATH
```

Preflight is local and does not call the model. It checks tools, resource limits, pinned pricing age, freshness and remaining budget. It does not verify credentials, account credit or model access.

## Launch explicitly

This command makes paid API calls. Configure `OPENAI_API_KEY` securely, or use a file containing only the key.

```sh
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
```

Model requests use `service_tier="default"`. All model prompts, tool feedback, reasoning and final reporting count against the configured cap. Framework preparation in this chat and compilation/benchmark CPU are outside the model-spend accounting scope.

The controller reserves before dispatch and settles actual API usage. Unknown usage retains the reservation and blocks the campaign. CLI-prepared runs have a two-hour deadline by default and cannot resume automatically. A time or budget limit may stop work before the whole dollar balance is spent. Context rolls over into a same-run checkpoint before the 64,000-token request ceiling; a checkpoint that itself exceeds that ceiling still stops safely.

## Continue beyond acceptance

[Shared rules](RULES.md) ask the agent to keep improving after API acceptance. `finish` is available in the final 120 seconds or when admission capacity is exhausted. Architecture, debugging, tests and optimization choices are the agent's own. Periodic validated tags preserve progress. If any API requirement fails, performance is skipped and earns zero credit; API failures also reduce correctness credit. Numeric milestone weights are not yet defined.

For an existing campaign after a framework revision, preserve its ledger and prepare fresh runs:

```sh
python3 -m toksec upgrade --campaign .runs/http-campaign
python3 -m toksec prepare --campaign .runs/http-campaign --level 1
```

Upgrade records old/new framework fingerprints and retains all charges. It refuses unresolved usage. Old runs stay frozen and are not resumed under changed prompts.

The [first Rust results](results/2026-11-12-luna-rust-http/README.md) motivated this policy. Stage 1 passed its initial checks but later had restart failures. Stage 2 passed its checks but had substantial load failures and finished early. Neither result establishes reliable high-concurrency service or security.

## Inspect and verify

```sh
python3 -m toksec export --run RUN_PATH
python3 -m unittest discover -s tests -v
```

`result.json` points to immutable candidate source, binary and acceptance report. Each candidate has its own directory. A failed build never replaces a working candidate. Before full acceptance, promotion must preserve every passed check and add another. After full acceptance, promotion requires a complete paired benchmark with no failures, bounded p99 regression and a reproducible throughput gain.

No framework can guarantee a working implementation before the agent's first successful submission. An empty or unsuccessful run reports that explicitly. Passing this finite public suite is not proof of complete correctness or security.

Read the [full walkthrough](docs/public-system.md), [implementation decisions](docs/system-plan.md) and [verification record](docs/system-verification.md). The original Python pilot remains available in the root modules and [recorded results](results/2026-11-11-luna-http-l1-pilot/README.md). It has a different contract and runner. Use the `python3 -m toksec` commands for the shared Rust campaign.

Stages 1 through 5 use the [visible/held-out split](docs/visible-and-held-out-tests.md). Builder feedback is smoke-only; development benchmarks are provisional. Final API grading remains comprehensive and gates final performance.

[C++ Stage 1 and Stage 2](docs/cpp-stages.md) use the same contracts and evaluation suites with main.cpp and only standard/system libraries. Select --language cpp when preparing or evaluating a C++ run.
