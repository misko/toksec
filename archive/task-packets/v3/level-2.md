# Level 2: Concurrent persistent HTTP

Contract version: rust-http-v3. Independent from-scratch task.

## Process API

Submit one UTF-8 main.rs, at most 1 MiB. Build with the pinned rustc in release mode. No Cargo build scripts, proc macros, downloads, subprocess servers, HTTP frameworks or HTTP parser libraries. Rust std and direct libc OS calls through declared FFI are permitted. For Level 5 only, system OpenSSL and zlib FFI are approved. Record unsafe usage in the final report.

Execute `/candidate/server --config /fixtures/server.conf`. Bind within two seconds. Config is UTF-8 key=value, one per line, with optional blank lines and # comments. Unknown keys, duplicate keys, missing keys and malformed values must exit nonzero before listening. All keys below are required. Ports are decimal; limits are positive integers except rate_per_second may be zero. Booleans are true or false. Paths are absolute. root must be an existing directory. Configuration values used by public checks are supplied by the controller.

```ini
listen=127.0.0.1:8080
root=/www
max_connections=8192
header_bytes=8192
header_timeout_ms=1000
idle_timeout_ms=2000
write_timeout_ms=2000
max_requests=100
pipeline_depth=16
```

## Complete wire API

Implement GET over HTTP/1.0 and HTTP/1.1 origin-form requests. Respond once and close with Connection: close.
A valid unknown method returns 405. Missing Host is permitted in this restricted profile. Versions other than 1.0 and 1.1 return 400.
Read fragmented requests and require CRLF. Reject bare LF, NUL, invalid header names, folded headers, malformed request lines and malformed headers with 400.
Reject Transfer-Encoding, duplicate Content-Length, invalid lengths and nonzero Content-Length with 400. A single decimal zero, including leading zeroes, is accepted.
Enforce header_bytes including the final CRLFCRLF; excess returns 431. header_timeout_ms is an absolute deadline from accept, even if bytes keep arriving. Close at deadline; 408 is optional.
Strip the query, decode path percent escapes once as UTF-8, reject malformed escapes, fragments, absolute-form, NUL and backslash with 400.
Return 403 for decoded '..' components, symlinks in any component, directories and nonregular files. Missing files return 404. Trailing slash on a regular file returns 403 or 404.
Serve immutable regular files only beneath root. Preserve exact bytes for empty, binary and large files. Explicit Content-Length is mandatory and must match body bytes. No Transfer-Encoding in local responses.
Error bodies may be empty. Successful local responses may use application/octet-stream. Disconnects and malformed clients must not stop later valid service.
Concurrency is optional, but the public benchmark measures service at both 256 and 4096 active clients. Bound every buffer and open descriptor.

Support GET and HEAD. For HEAD return the same status and representation headers as GET, including the GET Content-Length, with no body.
HTTP/1.1 persists by default; Connection: close overrides it. HTTP/1.0 closes by default and need not support keep-alive. Include Connection: keep-alive or close explicitly.
Parse Connection tokens case-insensitively. Handle sequential requests and up to pipeline_depth pipelined requests in order. A response body must never be confused with the next header.
Close after max_requests responses, advertising close on the final response. Close idle connections after idle_timeout_ms. An incomplete request has its own absolute header deadline from its first byte; idle waiting uses the idle deadline.
Malformed requests return their error then close. GET and HEAD bodies remain forbidden. Backpressure must bound queued requests and response data; pause reads rather than grow queues beyond pipeline_depth.
Serve concurrent clients independently. Slow input or output on one connection must not block ordinary clients. Enforce max_connections and write_timeout_ms. Refuse or close excess connections without crashing.
Level 1 always-close and GET-only rules are replaced by these rules; all other local file and parsing requirements are included in this package.

## Public acceptance suite

Every listed check is mandatory. The complete executable suite is supplied in public-suite/. The acceptance report names each check. No hidden tests are used. You may implement and run additional tests.

- `bootstrap`: A working server serves an ordinary file, empty file and a missing-file error.
- `files`: Exact ordinary, empty, binary and 2 MiB files; missing file returns 404.
- `query-and-decoding`: Query does not select a different file; strict one-pass percent decoding.
- `confinement`: Traversal and symlinks are forbidden; nonregular objects and trailing file slash are not served.
- `fragmentation`: A request split at each byte remains valid.
- `syntax`: Malformed request/header/version, folded headers and unsupported methods have explicit errors.
- `request-framing`: Local request bodies, ambiguous lengths and transfer coding are rejected; decimal zero is valid.
- `header-limit`: Header section exactly 8192 bytes is accepted; 8193 bytes returns 431.
- `absolute-header-deadline`: Slow fragments cannot extend the one-second absolute header deadline.
- `disconnect-recovery`: Incomplete and abandoned clients do not prevent later valid service.
- `head`: HEAD has GET headers and length with no body, including missing files.
- `persistent-pipeline`: Persistent and pipelined responses retain order and exact framing.
- `connection-semantics`: HTTP/1.0 defaults to close; mixed-case Connection tokens override HTTP/1.1 persistence.
- `connection-limits`: Close after 100 requests; close idle persistent connections after two seconds.
- `slow-client-fairness`: A slow sender and a stalled large-file reader do not block ordinary requests.
- `configuration`: Invalid, duplicate, missing and unknown config values exit nonzero before serving.

## Benchmarks

Each workload uses 256 or 4096 active clients, one request outstanding per client, split over four trusted load-generator workers. Five rounds, each with one second of warmup and three seconds of measurement. Per-request deadline is two seconds. Fresh-connection latency includes connect; persistent latency includes reconnect when needed. TLS latency includes handshake when connecting. Failures and timeouts are counted, never retried invisibly. Responses must have the expected status and exact bytes after decompression.

Report valid requests/s, payload bytes/s, p50/p95/p99 successful request latency, failures, timeouts, per-round spread, server CPU and peak RSS, client CPU and event-loop lag. Closed-loop results are conditional on the workload; they are not an open-loop arrival-rate guarantee. Excess generator lag or CPU saturation marks the result inconclusive for optimization. Throughput counts completions inside the measurement window; latency and error totals also include the bounded drain of requests started inside it.

All public checks must pass for full acceptance. A working partial must retain every previously passed check. Optimize throughput without increasing failures, exceeding resource limits, or worsening p99 by more than 5% in any workload. Compare incumbent/challenger in alternating rounds. Require separation of throughput ranges and at least a 5% gain in geometric-mean goodput. If evidence is noisy, keep the incumbent. A partial benchmark never qualifies for promotion.

Acceptance starts sustained improvement. The controller permits finish only in its finalization window or when model admission capacity is exhausted. It exports the retained candidate with any failed revalidation warning. Report unsupported capabilities explicitly.

| Workload | Clients | Bytes | Connection | Transport |
|---|---:|---:|---|---|
| fresh-4096-256 | 256 | 4096 | fresh | HTTP |
| fresh-65536-256 | 256 | 65536 | fresh | HTTP |
| persistent-4096-256 | 256 | 4096 | persistent | HTTP |
| persistent-65536-256 | 256 | 65536 | persistent | HTTP |
| fresh-4096-4096 | 4096 | 4096 | fresh | HTTP |
| fresh-65536-4096 | 4096 | 65536 | fresh | HTTP |
| persistent-4096-4096 | 4096 | 4096 | persistent | HTTP |
| persistent-65536-4096 | 4096 | 65536 | persistent | HTTP |

## Test suggestions

Start with a runnable file-serving path. Exercise arbitrary TCP fragmentation, path confinement, malformed messages, timeout boundaries, slow senders/readers, disconnect recovery and exact response framing. For applicable features test HEAD body suppression, pipelining order, host separation, proxy retries, cache isolation, TLS, invalid reload and graceful drain. Use small executable increments. Ask budget_status before substantial work. Never weaken required behavior for performance.

## Implementation guidance

Model each connection with explicit read-header, write-header, write-body and idle states. At 4096 clients a thread and a large buffer per connection can exceed the memory limit. Consider nonblocking sockets with epoll/poll and small bounded buffers. Track deadlines independently and preserve pipeline order under partial writes.

Use the first small fraction of the wall budget to submit a runnable bootstrap. Spend the next work on failed public checks. Once all pass, measure a baseline, make one focused optimization, and compare. These are suggestions, not hidden acceptance rules. Every submission is archived. Failed compiles, lost checks and inconclusive performance leave the incumbent intact. There is no supplied server implementation and no guarantee of success before the first working submission.

The run has 30 minutes by default, independent of the shared dollar cap. A complete paired benchmark needs time proportional to this level’s workload matrix. When it no longer fits, continue with bounded security tests and restart validation until the finalization window. Report unmeasured changes honestly.

## Continue after acceptance

Your objective is the best validated implementation attainable within this run's remaining capacity. Passing the public suite is the beginning of improvement work. It is not permission to finish. One or two optimization attempts are not a stopping condition. Continue until the controller's finalization window or admission limit.

Preserve interface correctness first. Keep all public checks passing. Improve reliable service before chasing successful-request throughput. Then hill climb performance and investigate security risks. A candidate that loses correctness or fails to start cannot replace a working incumbent.

Repeat this loop while capacity remains:

1. Read budget_status and the latest results. Identify one concrete bottleneck, reliability failure or security hypothesis. State the mechanism and the expected observable result. Record it with record_iteration.
2. Make one bounded change. Submit complete source through submit_candidate. Do not stack untested changes. Work from the retained implementation unless explicitly investigating a failed challenger.
3. Test the hypothesis. Use the public checks, sandboxed run_tests, restart validation, and the full benchmark when it fits. Compare evidence, not intuition. Record observed results and the next hypothesis. The controller owns promotion; your journal does not declare a win.
4. Keep an improvement only when supported by the controller's gates. Otherwise keep the incumbent and change the hypothesis or category. Never weaken checks, hardcode fixture responses or conceal failures.
5. Continue. An inconclusive benchmark is not success and is not a reason to finish. Investigate the measurement limit or switch to security, stability, bounded resource use and test coverage. Do not repeatedly benchmark unchanged code or repeatedly ask to finish.

For performance, first address crashes, failed requests and timeouts under the declared 256/4096-client workloads. Then consider architecture, bounded queues, allocation/copy costs, syscall counts, backpressure, connection reuse and tail latency. Explain how a change should help before running it. Never call a generator-limited measurement a server speedup.

For security, review and exercise parser framing and integer boundaries, path normalization and symlink handling, allocation limits, slow clients, disconnect handling and descriptor/thread exhaustion. At applicable levels add pipeline desynchronization, host separation, upstream framing/retry behavior, cache isolation, TLS state handling and atomic reload. Use executable regression tests where possible. A review claim alone is not evidence of a fix. A passing finite suite is not proof that the server is secure.

Use run_tests for bounded tests of your Rust parsing, routing and resource-management logic. Use revalidate_candidate for three independent sandbox starts and complete public checks. Inspect server diagnostics. Treat a failed restart as a reliability defect even if a previous process passed every check. Revalidate the retained implementation during stabilization.

If the remaining time cannot fit a full paired benchmark, choose useful smaller work: a focused parser boundary test, malformed-input cases, overflow/property tests, a review of unsafe/FFI ownership with an executable test, or fresh-start validation. Preserve unpromoted security fixes and their evidence in candidate snapshots and the journal; do not claim an unpromoted change is the final artifact. Do not spend the final window starting a task that cannot finish.

Keep concise durable notes through record_iteration. Include hypothesis, change, observed evidence, verdict and next action. The controller may replace old conversation history with a checkpoint containing this contract, retained/latest source, reports and your recent notes. This preserves the same run and spending ledger; it does not grant a fresh budget or import another level's work.

Call finish only when budget_status reports can_finish=true. Use the final report to distinguish accepted behavior, measured performance, inconclusive results, demonstrated security fixes, unresolved risks and unpromoted experiments. If the controller interrupts work, the retained artifact and evidence must still be usable. Never claim maximal performance, complete security or completion merely because the minimum API works.
