# Stage 5 Rust reference

The delivered `main.rs` implements the Stage 5 plaintext HTTP contract from scratch using Rust's standard library and direct Linux system calls. The frozen source passes all 35 required host API checks and twelve additional focused test groups. The initial supplemental matrix exposed connection-burst failures; backlog and exchange-limit fixes produced zero measured request failures/timeouts in a second matrix, whose overall result remained ineligible because of generator saturation and one workload with warmup failures. A further FIFO fairness repair has a retained failing-before/passing-after regression. The current source's performance remeasurement is delegated to the coordinating parent.

## Frozen source and evidence

- Source SHA-256: `db022677b2f7361c45311a1ac0fd981e8271b9a71ae0323d2e3334f1aa889e07`.
- Final compiled executable SHA-256: `b01cc669433c2a39f81e69567f4729e663c9d49fc8615107a69cd105e3a94951`.
- Final full API result: `.runs/references/stage-05-rust/api-005/result.json`; **35 passed, 0 failed**, successful optimized build, no compiler diagnostics, server exited normally.
- Final supplemental correctness evidence: `.runs/references/stage-05-rust/focused-006/result.json`; **12 groups passed**, server exited normally, 512 MiB address-space limit and 16,384 descriptor limit applied.
- Earlier retained API results: `api-001/result.json` through `api-004/result.json` beneath the same run directory; all passed 35/35. Earlier focused results remain in `focused-001/result.json` and `focused-002/result.json`, each passing six groups; `focused-003/result.json`, passing nine; and `focused-004/result.json`, passing eleven.
- Earlier source hashes: API-001 `d9c4b224979348137ac55302488b24a693ce5ab0812a2139d4c6b441315c8977`; API-002 `d8f49e6b14c66ac799bbe4067927b5d237e81a081b229d2ee0fe019465be57b9`. The evaluator preserves each compiled source in its `candidate/main.rs`.
- Initial matrix source: API-003 `100101234605e960e002b5fc3508560362ea99aae61ad6b025bcdbe7c2ce1dc1`. A further checkpoint is `.runs/references/stage-05-rust/pre-backlog-queue-001/main.rs`.
- Backlog/exchange-limit matrix source: API-004 `61d9d4dcce601dee59d27579edc7805ad998b1522b615429b428147236c547bb`; checkpoint `.runs/references/stage-05-rust/pre-fifo-001/main.rs`.
- Deliberate failing-before FIFO regression: `.runs/references/stage-05-rust/focused-005-fifo-before/result.json`, API-004 source. Eleven groups pass; the added FIFO test fails because `/fair/new` reaches the upstream ahead of `/fair/old`. The same regression passes against API-005 in `focused-006`.

The final command was run from the repository root:

```sh
taskset -c 9,23 python3 evaluate.py --section api --level 5 --language rust --source references/stage-05/rust/main.rs --output .runs/references/stage-05-rust/api-005
```

The API evaluator was allowed CPUs 9 and 23; its server selects CPU 9, and CPU 23 supplies the separate upstream CPU required by the Stage 5 API driver. Standalone development compilation, including a successful final-source build retained at `.runs/references/stage-05-rust/compile-final-003/server`, was explicitly pinned to CPU 9. The evaluator's integrated compilation inherits its two-CPU allowance. No API model calls or further agents were started. No agent-generated performance traffic ran alongside the parent's measurements.

## Architecture and contract handling

A single level-triggered `epoll` loop owns nonblocking downstream and upstream TCP sockets. Connections progress through reading, waiting for an upstream slot, proxying and writing states. Each downstream executes one request at a time, which stays within every positive configured `pipeline_depth`; additional pipeline bytes remain in bounded input or kernel buffers. This preserves response order without allocating a parsed pipeline queue. After `TcpListener::bind`, an explicit `listen` call raises its default 128 backlog to `max(128,max_connections)`, capped by the OS; the focused test observes the host cap of 4,096.

Headers are parsed as bytes with strict request-line, CRLF, token-name, value and framing checks. Values may contain non-UTF-8 bytes. Header deadlines begin with the first input byte; idle waits, body-upload inactivity, upstream completion and stalled writes have separate deadlines. Deadline maintenance runs at roughly 10 ms intervals. HTTP/1.0 and HTTP/1.1 persistence, explicit connection headers, maximum request counts, HEAD and ordered pipelining are implemented. Completed final responses send FIN and discard already queued surplus input before closing to avoid resetting a valid response when requests exceed `max_requests`.

Local routing validates and decodes the path once, checks hosts, resolves redirects, aliases and indexes, then opens every filesystem component relative to its parent with `openat(O_NOFOLLOW)`. Nonregular files and symlinks are rejected. A bounded 256-entry representation cache holds immutable file descriptors and metadata; `sendfile` streams bodies without copying whole files into connection memory. ETags, MIME types, conditionals, byte ranges and HEAD use the same selected representation.

Proxy uploads support bounded Content-Length and incremental chunk decoding with bounded trailers. Upload bytes remain in the request buffer and are sent separately from upstream request headers, avoiding a duplicate full upload allocation. Upstream responses support strict Content-Length and chunked framing. Response bodies are decoded once, bounded by `body_bytes`, and moved into a shared `Arc<Vec<u8>>` for output and optional caching. Declared Content-Length bodies reserve their exact length, avoiding geometric allocation growth that could almost double 64 KiB buffers. No downstream response is sent until upstream framing and the complete body have been validated.

Upstream selection rotates across configured endpoints; healthy HTTP/1.1 sockets are reused. At most **64 exchanges per endpoint** may be active. All new upstream exchanges and retries join the endpoint FIFO; only the dispatcher starts work through a separate start helper. This prevents an immediate persistent/pipelined continuation from taking a just-freed slot ahead of existing waiters. Downstreams retain their single parsed request while waiting. Completion releases a slot and starts the oldest queued work, usually over a reused socket. The upstream deadline starts when an exchange actually starts. Queued requests recheck cache before using a slot. Idle pooled sockets are capped at **256 globally** and expire on the configured idle interval. GET/HEAD may retry once on the next endpoint before downstream output; POST never retries. Both directions remove standard hop-by-hop fields and fields named by Connection. Active and queued requests retain their configuration snapshot, including when a reload changes the number of upstream endpoints. Responses from a previous snapshot cannot populate the new cache.

The cache keys HTTP scheme, normalized host authority, path and query, with Accept-Encoding variants when requested by Vary. It applies the specified authorization, cookie, public/max-age, private/no-store and unsupported-Vary bypasses. Expiry is capped by `cache_ttl_ms`; HEAD may read an existing GET entry but cannot populate it. FIFO eviction keeps cached body bytes within `cache_bytes`; an additional 1,024-entry ceiling bounds metadata and empty-body entries. Cache-hit bodies are shared among downstreams.

Configuration validation rejects unknown, duplicate, missing or malformed settings and invalid roots. SIGHUP constructs a complete replacement before committing it, rejects changed listener addresses, flushes cache and representation state, and resets limiter state. A monotonic global token bucket emits 429 with Retry-After. SIGTERM closes the listener, finishes active proxy/file responses until the drain deadline and then exits.

## Additional correctness checks

The retained supplemental correctness script is `.runs/references/stage-05-rust/focused-006/probe.py`. It uses ephemeral listeners and its own fixtures. Its groups cover:

1. A client half-closing its write side while waiting for a delayed proxy response.
2. A 400-request burst with `max_requests=2`, verifying both final responses and clean EOF without TCP reset.
3. Percent-decoded UTF-8 and a percent-escaped newline filename, plus empty-file range edge cases.
4. Unsupported/ambiguous upstream transfer framing, malformed chunks, valid chunk extensions/trailers, opaque response header bytes and invalid upload trailers.
5. Reload while an upstream request is active, changing from two endpoints to one, then rejecting a listener-address reload.
6. Abandoned proxy clients followed by repeated valid requests, exercising descriptor reuse and recovery.
7. A controlled 160-request mix of GET, HEAD and POST to one endpoint: exactly 64 simultaneous exchanges, 64 distinct upstream sockets, all exact responses, and reuse across queued requests.
8. A controlled 160-request cacheable batch: 64 initially active exchanges, with the queued remainder satisfied by cache, and 64 total upstream requests.
9. Direct observation of a 4,096 listener backlog via `ss`, after requesting the configured 8,192 connection limit.
10. A cacheable response completing after an upstream reload cannot repopulate the new cache; subsequent requests use and cache the new endpoint's response.
11. A reload with 64 active and 96 queued proxy requests: all existing requests finish against their original endpoint snapshot; the next request uses the new endpoint.
12. FIFO ordering with 64 held exchanges, an older queued request and a buffered continuation on the connection whose response completes first. A token-bucket dispatch barrier proves the older request was dispatched before releasing the first response. The older request must be the next upstream admission. The previous binary reproducibly fails this test; the delivered binary passes.

These supplement the full host cases for routing, file confinement, byte-exact large files, backpressure, deadlines, cache variants and limits, rate limiting, reload and graceful shutdown. Finite tests do not establish exhaustive correctness.

## Memory and performance status

For a declared 64 KiB Content-Length proxy response, active exchange body storage is one exact 64 KiB allocation plus at most one 16 KiB upstream read buffer and small request/header/state allocations. With two endpoints and 64 exchanges per endpoint, that part is about **10 MiB**; completed responses waiting on downstream writes have separate bounded per-response storage. This is an allocation review, not a measured RSS result for the updated source. File responses stream; cache hits share their body allocation; idle upstream and local-file descriptor caches have independent small ceilings.

Per-request proxy body storage is bounded by `body_bytes`, but simultaneous maximum-size uploads/responses can still exhaust the process-wide 512 MiB limit. The implementation does not contain a separate global body-memory admission mechanism. The configured connection ceiling also shares the operating-system descriptor limit with active upstreams; an upstream socket creation failure becomes a gateway error. These general resource extremes have not been validated by the supplemental tests.

The coordinating parent will remeasure the updated frozen source with exclusive benchmark resources. Its throughput, latency, failures/timeouts, CPU/RSS, round spread and measurement eligibility remain pending. The initial-source evidence below must not be attributed to the updated source. All canonical full-matrix and five-round performance conclusions remain pending. The architectural choices above are not evidence of a speedup.

## Unsafe / FFI disclosure

Unsafe blocks declare and invoke Linux `epoll_create1`, `epoll_ctl`, `epoll_wait`, `openat`, `socket`, `connect`, `listen`, `sendfile`, `signal` and `close`; construct owned Rust descriptors from successful raw-descriptor returns; and pass correctly laid-out IPv4/IPv6 socket addresses and packed epoll records. Signal handlers only store atomic flags. File descriptors otherwise use Rust ownership/RAII. No third-party libraries, compression, encryption, TLS, HTTP frameworks, dynamic loader APIs or subprocess servers are used.

## Retained initial-source supplemental matrix

Evidence: `.runs/references/supplemental-batch-v2-001/stage-05-rust/result.json`, source `100101234605e960e002b5fc3508560362ea99aae61ad6b025bcdbe7c2ce1dc1`. The parent ran all 24 workloads with one round per workload and CPUs 10–15. The result finalized and rechecked candidate/tool identity before source edits. It is a native closed-loop supplemental diagnostic, explicitly **not canonical and not comparable to official asyncio metrics**. Overall eligibility was false; the server remained alive. A single round supplies no measured between-round spread.

The initial listener inherited Rust's backlog 128, verified in binary disassembly. Thousands of simultaneous proxy requests could also initiate thousands of upstream connections. The observed high-client failures motivated the backlog and exchange-queue corrections; the original data are retained and no failed result is discarded. Eligibility can also fail through generator lag or saturation even where request failures are zero.

Each row gives valid requests/s, payload MiB/s, successful-request p50/p95/p99 milliseconds, measured failures/timeouts, measured server CPU utilization, sampled server peak RSS KiB, and eligibility. Full worker CPU/lag, upstream utilization, warmup failures and per-round records remain in the JSON. The single round makes min/max request-rate spread equal trivially; it does not establish repeatability.

| Workload | RPS | MiB/s | p50/p95/p99 ms | Fail/timeout | Server CPU | Server RSS KiB | Eligible |
|---|---:|---:|---|---:|---:|---:|---|
| fresh-4096-256 | 43048.0 | 168.2 | 3.1/4.1/7.2 | 0/0 | 97.1% | 2884 | yes |
| fresh-65536-256 | 28034.0 | 1752.1 | 4.1/11.0/21.3 | 0/0 | 82.4% | 3068 | no |
| persistent-4096-256 | 74399.3 | 290.6 | 3.1/6.0/9.0 | 0/0 | 97.4% | 3084 | yes |
| persistent-65536-256 | 59802.3 | 3737.6 | 4.0/7.2/9.5 | 0/0 | 100.0% | 3084 | yes |
| fresh-4096-4096 | 33612.0 | 131.3 | 5.1/1032.7/1239.9 | 355/355 | 97.3% | 5636 | no |
| fresh-65536-4096 | 27756.0 | 1734.8 | 8.6/1042.7/1287.2 | 1610/1610 | 96.7% | 5636 | no |
| persistent-4096-4096 | 51393.7 | 200.8 | 59.1/64.8/127.9 | 541/541 | 93.0% | 5792 | no |
| persistent-65536-4096 | 48695.7 | 3043.5 | 53.3/66.8/73.1 | 857/857 | 98.4% | 5792 | no |
| routed-4096-256 | 66665.0 | 260.4 | 3.7/6.3/8.3 | 0/0 | 98.2% | 5792 | yes |
| routed-65536-256 | 53315.0 | 3332.2 | 4.1/10.2/11.8 | 0/0 | 88.3% | 5792 | yes |
| routed-4096-4096 | 57373.3 | 224.1 | 32.2/58.4/168.7 | 1627/1627 | 96.2% | 5792 | no |
| routed-65536-4096 | 49203.0 | 3075.2 | 77.1/87.0/100.9 | 0/0 | 98.2% | 8596 | no |
| proxy-4096-256 | 18439.7 | 72.0 | 12.3/20.6/52.0 | 0/0 | 79.2% | 8600 | yes |
| proxy-65536-256 | 8231.0 | 514.4 | 24.2/57.2/108.1 | 0/0 | 70.8% | 8676 | yes |
| proxy-4096-4096 | 12477.0 | 48.7 | 70.8/598.1/1528.5 | 3751/571 | 93.8% | 11160 | no |
| proxy-65536-4096 | 6899.3 | 431.2 | 118.0/734.1/1566.9 | 4419/1281 | 89.8% | 11164 | no |
| cache-hit-4096-256 | 66246.7 | 258.8 | 3.7/6.3/8.1 | 0/0 | 99.1% | 11164 | yes |
| cache-hit-65536-256 | 37185.0 | 2324.1 | 6.6/9.1/14.2 | 0/0 | 100.1% | 11164 | yes |
| cache-miss-4096-256 | 17142.7 | 67.0 | 14.6/22.0/25.3 | 0/0 | 78.0% | 11164 | yes |
| cache-miss-65536-256 | 10245.3 | 640.3 | 23.6/34.9/50.6 | 0/0 | 83.4% | 11164 | yes |
| cache-hit-4096-4096 | 56966.3 | 222.5 | 56.1/63.2/77.3 | 594/594 | 99.5% | 11164 | no |
| cache-hit-65536-4096 | 33976.7 | 2123.5 | 86.6/130.2/766.3 | 327/327 | 98.8% | 11164 | no |
| cache-miss-4096-4096 | 11088.0 | 43.3 | 44.1/600.1/1344.9 | 4548/613 | 87.7% | 11180 | no |
| cache-miss-65536-4096 | 7791.3 | 487.0 | 107.5/1127.0/1683.1 | 4596/1108 | 95.2% | 11192 | no |

## Retained backlog/exchange-limit supplemental matrix

Evidence: `.runs/references/supplemental-batch-v2-rust-fixed-001/stage-05-rust/result.json`, API-004 source `61d9d4dcce601dee59d27579edc7805ad998b1522b615429b428147236c547bb`. All 24 one-round workloads finalized and the candidate/tool identity rechecks completed before the FIFO change. This is again supplemental native evidence, not a canonical five-round result and not a measurement of the final FIFO-fixed source. All workloads had **zero measured request failures and zero measured timeouts**. Overall eligibility remained false: generator saturation/lag affected three workloads, and `cache-miss-4096-256` had warmup failures. No thresholds were relaxed.

| Workload | RPS | MiB/s | p50/p95/p99 ms | Fail/timeout/warmup | Server CPU | Server RSS KiB | Eligible |
|---|---:|---:|---|---:|---:|---:|---|
| fresh-4096-256 | 32797.0 | 128.1 | 7.4/10.1/19.8 | 0/0/0 | 96.3% | 3072 | no |
| fresh-65536-256 | 30165.7 | 1885.4 | 8.4/10.0/11.9 | 0/0/0 | 99.6% | 3072 | yes |
| persistent-4096-256 | 68032.7 | 265.8 | 3.2/6.1/9.0 | 0/0/0 | 93.4% | 3092 | yes |
| persistent-65536-256 | 56998.3 | 3562.4 | 4.1/7.6/9.7 | 0/0/0 | 99.8% | 3092 | yes |
| fresh-4096-4096 | 29713.0 | 116.1 | 132.9/146.2/151.3 | 0/0/0 | 98.1% | 10336 | yes |
| fresh-65536-4096 | 25876.3 | 1617.3 | 136.9/264.5/615.1 | 0/0/0 | 92.9% | 8456 | no |
| persistent-4096-4096 | 24485.3 | 95.6 | 150.5/163.9/324.4 | 0/0/0 | 47.2% | 8588 | yes |
| persistent-65536-4096 | 36546.7 | 2284.2 | 80.5/175.2/181.5 | 0/0/0 | 73.2% | 8592 | yes |
| routed-4096-256 | 54772.7 | 214.0 | 3.6/11.1/16.4 | 0/0/0 | 79.9% | 8592 | yes |
| routed-65536-256 | 54670.7 | 3416.9 | 4.1/9.0/11.5 | 0/0/0 | 94.7% | 8592 | yes |
| routed-4096-4096 | 49122.3 | 191.9 | 70.0/152.4/158.9 | 0/0/0 | 86.0% | 8592 | yes |
| routed-65536-4096 | 51164.3 | 3197.8 | 78.3/87.1/99.7 | 0/0/0 | 99.3% | 8592 | yes |
| proxy-4096-256 | 20752.0 | 81.1 | 9.0/15.1/22.3 | 0/0/0 | 73.3% | 8592 | yes |
| proxy-65536-256 | 9566.7 | 597.9 | 25.0/40.8/56.0 | 0/0/0 | 84.1% | 8648 | yes |
| proxy-4096-4096 | 19072.0 | 74.5 | 204.9/252.8/265.0 | 0/0/0 | 93.9% | 10428 | yes |
| proxy-65536-4096 | 8632.7 | 539.5 | 412.3/473.3/485.0 | 0/0/0 | 93.2% | 10548 | yes |
| cache-hit-4096-256 | 75289.3 | 294.1 | 3.1/6.0/7.5 | 0/0/0 | 98.8% | 10548 | yes |
| cache-hit-65536-256 | 42241.3 | 2640.1 | 5.9/10.1/12.8 | 0/0/0 | 96.3% | 10548 | yes |
| cache-miss-4096-256 | 27274.0 | 106.5 | 8.1/11.0/15.7 | 0/0/114 | 90.1% | 10548 | no |
| cache-miss-65536-256 | 9441.3 | 590.1 | 18.0/23.1/40.0 | 0/0/0 | 65.4% | 10548 | yes |
| cache-hit-4096-4096 | 66279.0 | 258.9 | 60.3/67.8/74.5 | 0/0/0 | 96.7% | 10548 | yes |
| cache-hit-65536-4096 | 39262.3 | 2453.9 | 98.5/128.1/171.2 | 0/0/0 | 99.0% | 10548 | no |
| cache-miss-4096-4096 | 14126.0 | 55.2 | 207.1/636.0/659.0 | 0/0/0 | 65.4% | 10548 | yes |
| cache-miss-65536-4096 | 9879.0 | 617.4 | 354.9/458.9/464.2 | 0/0/0 | 93.9% | 10632 | yes |

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 20/24 rounds were eligible;
measurement failures: 641; warmup failures: 3967. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-05-rust/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
