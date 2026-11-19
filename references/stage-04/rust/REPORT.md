Stage 4 Rust reference is implemented and API-validated. The frozen source is `main.rs`, SHA-256 `42e880d1b878d4e2e45ba39ac9168f33ab339c355e9c53a642e421ac00610249`. Its final acceptance snapshot is `.runs/references/stage-04-rust/api-006/candidate/main.rs`, with the same hash. Rust 1.99.1 compiled it with edition 2021 and optimization level 3, without warnings. No dependencies, downloads, paid model calls, subprocess servers, or other reference implementations were used.

The server uses one Linux epoll loop, nonblocking downstream and upstream sockets, and bounded work per event. It explicitly sets the listen backlog to max(128, max_connections), capped by the platform integer range and kernel somaxconn. It processes one request per downstream connection at a time, so later pipelines wait in a bounded input buffer or the kernel receive queue. Local immutable files use cached file descriptors and sendfile; openat with O_NOFOLLOW on every component enforces root and alias confinement. The file cache contains at most 512 representations. Routing includes hosts, aliases, redirects, indexes, MIME types, stable quoted ETags, conditionals, and single byte ranges.

The proxy decodes Content-Length or chunked uploads, validates chunk extensions and bounded trailers, strips hop headers and Connection-named fields, rewrites Host, and buffers a bounded decoded upstream response before sending its Content-Length. It supports length, chunked and connection-delimited upstream bodies. Healthy HTTP/1.1 connections return to a round-robin upstream pool capped at 256 idle connections overall and 128 per upstream. At most min(64, max_connections) exchanges run per upstream authority. Every new proxy request and retry joins a FIFO queue; only the dispatcher claims an upstream slot, so later events cannot bypass existing waiters. The dispatcher keeps its old batch separate from retries generated during that pass, then places all older blocked entries before those new retries. This preserves order without requeue inversion while allowing another authority to progress independently. Generation tickets prevent stale entries from attaching to reused descriptors. Queued requests have the configured idle deadline, and reset downstream clients release pending/active resources promptly. GET and HEAD have at most one retry on the next upstream; POST is never replayed. Upstream connection/response completion uses an absolute deadline per attempt. Header deadlines are absolute; active uploads and output writes refresh their respective idle deadlines. Completed closing responses use a write-half shutdown and a short bounded input-drain period, preserving the final response when unread pipelines remain.

Unsafe FFI is limited to Linux epoll, nonblocking socket/connect/listen, openat, sendfile, setsockopt, SIGPIPE disposition, and ownership conversion of successful file descriptors into Rust File/TcpStream values. No HTTP, compression, encryption, TLS or dynamic-loading libraries are used. IPv4 and IPv6 numeric socket addresses are accepted; DNS upstream names are not resolved.

Full API evidence, retained in separate immutable candidate snapshots:

| Run | Source SHA-256 | Result |
|---|---|---|
| `.runs/references/stage-04-rust/api-001/result.json` | `30a22587b33ce783cd7b9019272a93e791efadab1a3f80e7b4a13b8e89b63dc2` | 31/31 passed |
| `.runs/references/stage-04-rust/api-002/result.json` | `9b9838d7d173e544f5fe913f1a62636056480426537ca1f2469d6521b4cf5293` | 31/31 passed |
| `.runs/references/stage-04-rust/api-003/result.json` | `ad38b0e2c8c52936a72da499ea2cc899532deb96c6134f343f09b1d69e0b57b9` | 31/31 passed; superseded by backlog/queue corrections |
| `.runs/references/stage-04-rust/api-004/result.json` | `80741961729de82a71ed2db33992575a40005eb2e4b6bfb4f64a1dba72a21c7e` | 31/31 passed; backlog and queue |
| `.runs/references/stage-04-rust/api-005/result.json` | `788a11b2c08e02b156de2981efe5efbe0eb37b1cbda72709745506f23a08d7cb` | 31/31 passed; superseded by FIFO fairness fix |
| `.runs/references/stage-04-rust/api-006/result.json` | `42e880d1b878d4e2e45ba39ac9168f33ab339c355e9c53a642e421ac00610249` | 31/31 passed; final source |

Each run executed the complete API CLI through evaluate.py, including configured connection-capacity, write-deadline and pipeline-backpressure cases and the invalid-configuration gate. An in-memory wrapper pinned only sandbox.build to CPU 7; the API process retained affinity 7,22 so the server used CPU 7 and its trusted upstream fixture used CPU 22. No evaluator or contract files were changed. Final API server diagnostics were empty and the server remained running.

Additional contract tests are retained in `focused.py`. `.runs/references/stage-04-rust/focused-001/result.json` passed 11 checks against source `dc002bdd7ecd7007f0228116b605770804d28d178cbd0bd2c03acf5f2eec5e8e`. `.runs/references/stage-04-rust/focused-002/result.json` passed all 12 checks against the exact api-003 executable at the earlier freeze. They cover GET failover to the next upstream, no POST replay, binary chunked uploads/responses, quoted chunk extensions and trailers, malformed framing/extensions, a progressing 1.35-second upload exceeding the header timeout, proxy HEAD followed by a pipelined GET, large HEAD representation length, opaque response header values, hop header removal, EOF-delimited bodies, status forwarding, escaped targets, an absolute upstream deadline despite trickled bytes, local/proxy half-closed clients, and a 300-request burst that receives exactly the configured 100 responses and clean EOF.

The pre-FIFO `.runs/references/stage-04-rust/focused-003/result.json` passed 13/13 checks against the exact api-005 binary and source hash. It repeats the 12 prior checks and adds a functional burst of 192 proxy requests, with exact per-request bytes, ordinary local service while requests wait, 48 request-side half closes, 32 reset clients, and successful recovery after the queue drains. The test asserts at most 128 simultaneous upstream exchanges for the configured two authorities. This is correctness/resource-bound evidence, not a throughput measurement.

`fairness_tests.rs` is a deterministic regression suffix appended to exact server snapshots and compiled with rustc --test inside the sandbox; it adds no hooks or fixture special cases to the delivered server. `.runs/references/stage-04-rust/fairness-003/result.json` retains the same seven tests against three sources. The accepted api-005 source fails three tests: a new request bypasses an old waiter, a retry bypasses old work on its next authority, and a retry generated during dispatch overtakes older blocked entries. An intermediate implementation which queued all new work but rotated old and new entries together fails the third test. The final api-006 source passes 7/7. The other tests verify direct dispatch without requeue inversion, independent progress for another authority, no POST replay, and no retry after the second attempt. Tests use explicit method calls and synthetic occupied-slot counts with sufficient configured client capacity, avoiding event-loop timing or load as the assertion mechanism. Earlier experimental regression artifacts remain in fairness-001 and fairness-002.

The final `.runs/references/stage-04-rust/focused-004/result.json` passed all 13 integration checks against the exact api-006 executable and source hash, including the queued burst, half closes, resets, framing and retry behavior.

Known-length response vectors reserve their declared size exactly. This avoids geometric vector growth retaining roughly 128 KiB for a 64 KiB representation whose first read also contains headers. For 4096 simultaneous 64 KiB buffered responses, payload storage alone is 256 MiB; with the configured two upstreams, at most 128 active upstream parser buffers add approximately 2 MiB at normal header sizes, plus connection and header metadata. This is an allocation review, not a peak-RSS measurement. Memory is bounded per connection by configuration, with bounded idle pools and file caching; there is no separate global payload admission budget. Extremely many simultaneous bodies near body_bytes can exceed the 512 MiB address-space allowance. DNS-name upstream authorities are unsupported; overload behavior at that extreme and IPv6 traffic have not received supplemental runtime validation.

The parent completed a one-round, full 16-workload native v2 diagnostic on the superseded api-003 source: `.runs/references/supplemental-batch-v2-001/stage-04-rust/result.json`. Before editing, its target was verified complete and its source hash was checked against the accepted snapshot and working source. This diagnostic is explicitly noncanonical and not comparable to the official asyncio metrics. It reported 11,802 measured failures, so it is evidence of a defect rather than performance success. Only 7/16 workloads were eligible. A single round cannot establish round spread or stability. The retained compact summary is `.runs/references/stage-04-rust/review-001/superseded-sweep-summary.json`.

The following table records that superseded source only. CPU is server CPU seconds during the measurement window, RSS is sampled server peak MiB, and warmup errors are separate from measured errors.

| Workload | valid req/s | p50/p95/p99 ms | errors/timeouts | warmup errors | CPU s | RSS MiB | eligible |
|---|---:|---|---|---:|---:|---:|---|
| fresh-4096-256 | 32131.3 | 4.0/7.3/9.5 | 0/0 | 94 | 2.91 | 2.81 | no |
| fresh-65536-256 | 31734.7 | 4.0/5.1/6.1 | 0/0 | 0 | 2.93 | 2.80 | yes |
| persistent-4096-256 | 70075.7 | 3.2/6.1/8.1 | 0/0 | 0 | 2.85 | 2.80 | yes |
| persistent-65536-256 | 55480.3 | 4.2/8.0/11.7 | 0/0 | 0 | 2.85 | 2.80 | yes |
| fresh-4096-4096 | 28466.7 | 9.0/1047.3/1277.3 | 895/895 | 683 | 2.99 | 4.84 | no |
| fresh-65536-4096 | 22035.0 | 11.0/1051.4/1276.4 | 1001/1001 | 1545 | 2.83 | 4.31 | no |
| persistent-4096-4096 | 60478.0 | 55.1/63.0/66.6 | 181/181 | 870 | 2.89 | 6.13 | no |
| persistent-65536-4096 | 52799.0 | 57.2/81.5/104.5 | 149/149 | 1052 | 2.96 | 6.13 | no |
| routed-4096-256 | 64069.3 | 3.1/10.1/12.0 | 0/0 | 0 | 2.50 | 6.13 | yes |
| routed-65536-256 | 42176.0 | 4.1/11.1/18.0 | 0/0 | 0 | 2.15 | 6.13 | yes |
| routed-4096-4096 | 48161.3 | 40.2/101.1/109.7 | 1100/1100 | 1616 | 2.35 | 6.13 | no |
| routed-65536-4096 | 52697.7 | 34.4/42.6/95.7 | 1285/1285 | 2266 | 2.98 | 6.13 | no |
| proxy-4096-256 | 11784.0 | 13.8/58.3/95.2 | 0/0 | 0 | 1.55 | 6.15 | yes |
| proxy-65536-256 | 5933.7 | 27.5/63.6/723.9 | 0/0 | 0 | 1.74 | 6.15 | yes |
| proxy-4096-4096 | 12023.3 | 36.0/565.0/1319.0 | 3739/1596 | 2607 | 2.59 | 6.93 | no |
| proxy-65536-4096 | 6983.3 | 140.6/1072.5/1517.0 | 3452/1392 | 2438 | 2.81 | 7.11 | no |

The persistent-65536-4096 diagnostic also flagged generator saturation/lag and is inconclusive on that dimension. The proxy rows did not flag generator or upstream saturation. The later api-005 sweep is recorded below; performance validation of the final FIFO-corrected api-006 source remains pending, and no speedup is claimed.

A controlled no-traffic socket inspection independently confirmed the backlog defect and correction. `.runs/references/stage-04-rust/backlog-002/result.json` records ss showing backlog 128 for api-003 and 4096 for the backlog-corrected api-005 binary under the normal max_connections=8192 configuration (the kernel caps the requested backlog). `.runs/references/stage-04-rust/backlog-001/result.json` retains the earlier isolated backlog-only snapshot as well. Inspection also identified unbounded bursts of new upstream connections as a plausible contributor to proxy deadline/status failures; the active-exchange cap and queue address that risk, but performance causation and improvement require the coordinated rerun. At the parent's request this agent started no benchmark and used only CPUs 7 and 22 for builds/API/focused diagnostics, avoiding the central measurement CPUs 10–21.

The parent subsequently completed another noncanonical one-round full matrix for api-005 at `.runs/references/supplemental-batch-v2-rust-fixed-001/stage-04-rust/result.json`. It has 14/16 eligible workloads, with zero measured and warmup failures across every 4096-client workload. Fresh 4 KiB/4096 was ineligible for generator lag. Proxy 64 KiB/256 recorded 107 measured failures (71 timeouts and 36 status errors) and 256 warmup failures, with generator lag of 108.091 ms flagged; that row is inconclusive for attributing the failures to the server. The direct admission/retry FIFO defect was identified independently by code review and reproduced by the deterministic tests, rather than inferred from that noisy row.

These metrics describe the superseded api-005 source only and remain noncanonical. CPU is server measurement-window seconds and RSS is sampled peak MiB.

| Workload | valid req/s | p50/p95/p99 ms | errors/timeouts | warmup errors | CPU s | RSS MiB | eligible |
|---|---:|---|---|---:|---:|---:|---|
| fresh-4096-256 | 31485.7 | 8.0/9.6/12.7 | 0/0 | 0 | 2.96 | 3.02 | yes |
| fresh-65536-256 | 27033.7 | 9.2/11.1/15.9 | 0/0 | 0 | 2.90 | 3.02 | yes |
| persistent-4096-256 | 92392.3 | 2.6/5.0/6.1 | 0/0 | 0 | 2.95 | 3.02 | yes |
| persistent-65536-256 | 62373.7 | 4.0/7.1/8.5 | 0/0 | 0 | 2.98 | 3.02 | yes |
| fresh-4096-4096 | 28256.3 | 138.5/152.4/156.1 | 0/0 | 0 | 2.97 | 4.32 | no |
| fresh-65536-4096 | 24536.0 | 158.1/180.9/183.9 | 0/0 | 0 | 2.92 | 4.32 | yes |
| persistent-4096-4096 | 69546.0 | 57.2/64.1/70.4 | 0/0 | 0 | 2.95 | 6.13 | yes |
| persistent-65536-4096 | 57260.3 | 69.9/75.9/78.1 | 0/0 | 0 | 2.97 | 6.13 | yes |
| routed-4096-256 | 97872.3 | 2.3/4.3/5.4 | 0/0 | 0 | 2.97 | 6.13 | yes |
| routed-65536-256 | 64684.3 | 3.9/7.0/8.1 | 0/0 | 0 | 2.99 | 6.13 | yes |
| routed-4096-4096 | 58400.7 | 68.6/74.8/83.0 | 0/0 | 0 | 2.95 | 6.13 | yes |
| routed-65536-4096 | 47461.7 | 83.8/93.8/105.7 | 0/0 | 0 | 2.93 | 6.13 | yes |
| proxy-4096-256 | 14974.7 | 12.1/33.1/57.4 | 0/0 | 0 | 1.87 | 6.15 | yes |
| proxy-65536-256 | 860.3 | 30.8/1022.0/1078.4 | 107/71 | 256 | 0.30 | 6.21 | no |
| proxy-4096-4096 | 14216.7 | 12.0/1096.0/1221.2 | 0/0 | 0 | 2.72 | 8.16 | yes |
| proxy-65536-4096 | 5510.0 | 26.0/1724.1/1761.1 | 0/0 | 0 | 2.59 | 8.36 | yes |

The implementation is API-validated and passes its retained supplemental checks. Performance validation of the revised source, complete five-round spread and stability, and a general proof of every English requirement remain unestablished.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 8/16 rounds were eligible;
measurement failures: 54; warmup failures: 61. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-04-rust/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
