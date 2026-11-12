# Toksec

Measure the cost of building a working server with an AI agent, then the cost of finding an exploit in that exact artifact.

The current system prepares five **independent Rust HTTP tasks**. Each starts from an empty candidate workspace and fresh model context. The agent receives its complete API, configuration, public acceptance checks, benchmark source and workload matrix before writing code. Levels share one campaign ledger, never a prior implementation.

| Level | Complete target | Performance workloads |
|---|---|---|
| [1](tasks/v2/level-1.md) | GET static files, strict framing, confinement and deadlines | Fresh HTTP |
| [2](tasks/v2/level-2.md) | Static GET/HEAD, persistent connections, pipelining and concurrent service | Fresh and persistent HTTP |
| [3](tasks/v2/level-3.md) | Hosts, routes, indexes, MIME types, ETags and ranges | Fresh and persistent HTTP |
| [4](tasks/v2/level-4.md) | Static/routing API plus reverse proxy, upstream reuse, request bodies and failure handling | HTTP plus proxy |
| [5](tasks/v2/level-5.md) | Previous capabilities plus TLS, cache, gzip, rate limiting, reload and graceful drain | HTTP, proxy, TLS and gzip |

Every mode runs with 4 KiB and 64 KiB bodies at **256 and 4096 active clients**. Five rounds report goodput, p50/p95/p99 latency, failures, timeouts, CPU, RSS and load-generator saturation. This is a defined nginx-inspired subset, not a quantitative claim of half of nginx.

## Prepare without spending

Requires Linux, Python 3.11+, Rust, GCC, Bubblewrap, nsenter, OpenSSL, system zlib, five available CPUs and a descriptor hard limit of at least 16384. Compilation and generated execution both use private namespaces. Host credentials are not mounted.

```sh
python3 -m toksec publish --output tasks/v2
python3 -m toksec init --campaign .runs/http-campaign
python3 -m toksec prepare --campaign .runs/http-campaign --level 1
python3 -m toksec prepare --campaign .runs/http-campaign --level 2
python3 -m toksec status --campaign .runs/http-campaign
```

Prepare prints a unique run path. Use that exact path for subsequent commands. Creating the campaign imports the recorded Python pilot's $0.01291213 conservative charge. The remaining balance starts at $4.98708787. Use **one campaign directory** for the entire experiment. Initializing another directory starts a separate accounting scope and does not carry later spending from this one.

```sh
python3 -m toksec preflight --run RUN_PATH
```

Preflight is local and does not call the model. It checks tools, resource limits, pinned pricing age, freshness and remaining budget. It does not verify credentials, account credit or model access.

## Launch explicitly

This command makes paid API calls. Configure `OPENAI_API_KEY` securely, or use a file containing only the key.

```sh
python3 -m toksec run --run RUN_PATH --key-file ~/.codexapi
```

Luna uses `service_tier="default"`. The campaign admits at most $5 of conservatively priced API usage and 10 million input-plus-output tokens, including the prior pilot. All measured prompts, tool feedback, reasoning and model reporting count. Framework preparation in this chat was not metered and is outside that accounting scope. Compilation and benchmark compute are separate.

The controller reserves before dispatch and settles actual API usage. Unknown usage retains the reservation and blocks the campaign. Runs have a 30-minute deadline by default and cannot resume automatically. A time, context or budget limit may stop work before the whole dollar balance is spent.

## Inspect and verify

```sh
python3 -m toksec export --run RUN_PATH
python3 -m unittest discover -s tests -v
```

`result.json` points to immutable candidate source, binary and acceptance report. Each candidate has its own directory. A failed build never replaces a working candidate. Before full acceptance, promotion must preserve every passed check and add another. After full acceptance, promotion requires a complete paired benchmark with no failures, bounded p99 regression and a reproducible throughput gain.

No framework can guarantee a working implementation before the agent's first successful submission. An empty or unsuccessful run reports that explicitly. Passing this finite public suite is not proof of complete correctness or security.

Read the [full walkthrough](docs/public-system.md), [implementation decisions](docs/system-plan.md) and [verification record](docs/system-verification.md). The original Python pilot remains available in the root modules and [recorded results](results/2026-11-11-luna-http-l1-pilot/README.md). It has a different contract and runner. Use the `python3 -m toksec` commands for the shared Rust campaign.
