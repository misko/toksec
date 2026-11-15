# Level 5: TLS and operational features

Contract version: rust-http-v2. Independent from-scratch task.

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
default_host=alpha.test
host_root=beta.test:/www/beta
alias=/assets/:/www/assets/
redirect=/old:/hello.txt
index=index.html
proxy_prefix=/proxy/
upstreams=127.0.0.1:8081,127.0.0.1:8082
upstream_timeout_ms=500
body_bytes=1048576
tls_listen=127.0.0.1:8443
tls_cert=/fixtures/cert.pem
tls_key=/fixtures/key.pem
cache_ttl_ms=1000
cache_bytes=4194304
gzip=true
rate_per_second=0
rate_burst=2
drain_timeout_ms=2000
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

Require exactly one valid Host on HTTP/1.1 requests; missing, duplicate or unknown hosts return 400. HTTP/1.0 without Host uses default_host.
Match Host case-insensitively after removing an optional decimal port. default_host uses root; host_root maps beta.test to its own root.
Match the exact redirect path before file routing and return 302 with Location. alias maps its path prefix to the configured filesystem prefix; enforce confinement within that prefix.
For a directory with a trailing slash serve index if it is a regular file. A directory without a trailing slash returns 301 to its slash form, preserving the query. A directory without index returns 403.
Map .html to text/html, .txt to text/plain, and other files to application/octet-stream.
Emit a stable quoted ETag on local 200 responses. Matching If-None-Match or '*' returns 304 with no body, Content-Length: 0 and the ETag. Conditional matching precedes Range.
Support one bytes range on GET/HEAD: N-M, N-, and -N. Clamp M to EOF. Satisfiable ranges return 206, exact bytes and Content-Range: bytes N-M/SIZE. Unsatisfiable ranges return 416 and Content-Range: bytes */SIZE. Malformed or multiple ranges return 400.
Range and conditional behavior applies to the selected host, alias and index representation. A HEAD response has no body even for a range or error.

For paths beneath proxy_prefix, strip the prefix and send an origin-form '/' plus the remainder to the upstream, preserving the query. Local routes retain their Level 3 semantics.
Proxy GET, HEAD and POST. Permit a single valid Content-Length body or Transfer-Encoding: chunked, but never both. Reject duplicate lengths, unsupported transfer codings and invalid chunk syntax with 400. Decoded bodies above body_bytes return 413. Decode chunks and optional bounded trailers; do not forward trailers.
Use round-robin upstream selection for consecutive healthy requests. Reuse healthy HTTP/1.1 upstream connections. Strip hop-by-hop headers and every header named by Connection in both directions. Rewrite Host to the selected upstream authority.
Forward end-to-end headers, status and exact decoded body. Upstream Content-Length and chunked bodies are supported. Emit a known Content-Length downstream; bound response bodies to body_bytes, returning 502 if exceeded. HEAD has no downstream body.
Reject ambiguous or malformed upstream framing with 502. Apply upstream_timeout_ms to connection and response completion. A GET/HEAD may retry once on the next upstream only before a downstream response begins. Never retry POST. Final transport/malformed failures return 502; final deadline expiry returns 504.
Keep downstream request/response order. Upstream failures and disconnected downstream clients must not leak unbounded connections or poison subsequent requests.

Serve the same API over HTTP and TLS on tls_listen, using the supplied PEM certificate and key and a maintained TLS library. Support TLS 1.2 or newer. SNI alpha.test and beta.test select the same certificate; Host still selects routing. Do not implement cryptography yourself.
Cache successful proxy GET responses with explicit Cache-Control: public,max-age=N, capped by cache_ttl_ms. Cache key includes scheme, host, path and query. Honor Vary: Accept-Encoding. Vary:* and any other Vary field bypass cache. Requests with Authorization and responses with Set-Cookie, private or no-store bypass cache.
Keep total cached body bytes within cache_bytes and evict entries when necessary. HEAD may use an existing GET entry but must not create an empty GET entry. Expired entries are fetched again; conditional cache revalidation is outside this level's v2 profile.
If gzip=true and Accept-Encoding permits gzip with nonzero quality, gzip local text representations at least 1024 bytes. Include Content-Encoding: gzip and Vary: Accept-Encoding; Content-Length is the compressed size. HEAD uses the same representation headers. Range responses remain uncompressed. Use zlib or an equivalent approved compression library.
When rate_per_second > 0, enforce a global token bucket shared by HTTP and TLS, refilled by monotonic time up to rate_burst. Rejected requests receive 429 and Retry-After. Benchmarks disable this limiter.
On SIGHUP reread the entire configuration atomically. An invalid reload retains the previous configuration. A valid reload changes roots, routing, cache and limiter settings for subsequent requests; flush cache. Listener addresses and TLS paths are immutable across reload and changes to them invalidate reload.
On SIGTERM stop accepting new connections, finish in-flight responses up to drain_timeout_ms, then exit. TLS and plain listeners both drain. Rate limiting, caching and reload must not break path confinement or HTTP framing.

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
- `hosts`: Host routing is case-insensitive; absent, duplicate and unknown HTTP/1.1 hosts fail.
- `routes-index-mime`: Exact redirects, prefix aliases, directory indexes and MIME types work.
- `etag`: Stable ETags and matching conditional requests return an empty 304.
- `ranges`: Closed, open and suffix byte ranges plus HEAD, invalid and unsatisfiable ranges.
- `proxy-get-and-post`: Proxy exact bytes and query; relay Content-Length and chunked POST bodies.
- `proxy-framing-and-hops`: Reject ambiguous uploads; strip hop-by-hop headers in both directions.
- `proxy-pool-and-errors`: Round robin, upstream reuse, malformed upstream rejection and timeout response.
- `proxy-no-post-retry`: An upstream disconnect after receiving POST must not replay the operation.
- `tls`: TLS >= 1.2 serves exact file bytes and Host routing with SNI.
- `gzip`: Negotiated gzip has correct bytes and Vary; q=0 and ranges remain uncompressed.
- `cache`: Cache hit, expiry, host/query isolation, no-store and authorization bypass.
- `cache-byte-limit`: Cache eviction keeps retained response body bytes within the configured capacity.
- `reload-and-rate-limit`: Valid reload changes roots atomically; invalid reload retains config; token bucket rejects excess.
- `graceful-stop`: SIGTERM finishes an in-flight response, closes listeners and exits within drain deadline.
- `configuration`: Invalid, duplicate, missing and unknown config values exit nonzero before serving.

## Benchmarks

Each workload uses 256 or 4096 active clients, one request outstanding per client, split over four trusted load-generator workers. Five rounds, each with one second of warmup and three seconds of measurement. Per-request deadline is two seconds. Fresh-connection latency includes connect; persistent latency includes reconnect when needed. TLS latency includes handshake when connecting. Failures and timeouts are counted, never retried invisibly. Responses must have the expected status and exact bytes after decompression.

Report valid requests/s, payload bytes/s, p50/p95/p99 successful request latency, failures, timeouts, per-round spread, server CPU and peak RSS, client CPU and event-loop lag. Closed-loop results are conditional on the workload; they are not an open-loop arrival-rate guarantee. Excess generator lag or CPU saturation marks the result inconclusive for optimization. Throughput counts completions inside the measurement window; latency and error totals also include the bounded drain of requests started inside it.

All public checks must pass for full acceptance. A working partial must retain every previously passed check. Optimize throughput without increasing failures, exceeding resource limits, or worsening p99 by more than 5% in any workload. Compare incumbent/challenger in alternating rounds. Require separation of throughput ranges and at least a 5% gain in geometric-mean goodput. If evidence is noisy, keep the incumbent. A partial benchmark never qualifies for promotion.

A build can finish after full acceptance and at least one evaluated optimization attempt, or when time/capacity is exhausted. The controller always exports the best accepted candidate. Report unsupported capabilities explicitly.

| Workload | Clients | Bytes | Connection | Transport |
|---|---:|---:|---|---|
| fresh-4096-256 | 256 | 4096 | fresh | HTTP |
| fresh-65536-256 | 256 | 65536 | fresh | HTTP |
| persistent-4096-256 | 256 | 4096 | persistent | HTTP |
| persistent-65536-256 | 256 | 65536 | persistent | HTTP |
| proxy-4096-256 | 256 | 4096 | persistent | HTTP |
| proxy-65536-256 | 256 | 65536 | persistent | HTTP |
| tls-4096-256 | 256 | 4096 | persistent | TLS |
| tls-65536-256 | 256 | 65536 | persistent | TLS |
| gzip-4096-256 | 256 | 4096 | persistent | HTTP |
| gzip-65536-256 | 256 | 65536 | persistent | HTTP |
| fresh-4096-4096 | 4096 | 4096 | fresh | HTTP |
| fresh-65536-4096 | 4096 | 65536 | fresh | HTTP |
| persistent-4096-4096 | 4096 | 4096 | persistent | HTTP |
| persistent-65536-4096 | 4096 | 65536 | persistent | HTTP |
| proxy-4096-4096 | 4096 | 4096 | persistent | HTTP |
| proxy-65536-4096 | 4096 | 65536 | persistent | HTTP |
| tls-4096-4096 | 4096 | 4096 | persistent | TLS |
| tls-65536-4096 | 4096 | 65536 | persistent | TLS |
| gzip-4096-4096 | 4096 | 4096 | persistent | HTTP |
| gzip-65536-4096 | 4096 | 65536 | persistent | HTTP |

## Test suggestions

Start with a runnable file-serving path. Exercise arbitrary TCP fragmentation, path confinement, malformed messages, timeout boundaries, slow senders/readers, disconnect recovery and exact response framing. For applicable features test HEAD body suppression, pipelining order, host separation, proxy retries, cache isolation, TLS, invalid reload and graceful drain. Use small executable increments. Ask budget_status before substantial work. Never weaken required behavior for performance.

## Implementation guidance

Get maintained-library TLS working before adding caching, compression and reload. Account for OpenSSL WANT_READ/WANT_WRITE states. Treat configuration as an immutable snapshot replaced after full validation. Give cache keys and byte accounting explicit types. Exercise cache isolation and shutdown before optimizing.

Use the first small fraction of the wall budget to submit a runnable bootstrap. Spend the next work on failed public checks. Once all pass, measure a baseline, make one focused optimization, and compare. These are suggestions, not hidden acceptance rules. Every submission is archived. Failed compiles, lost checks and inconclusive performance leave the incumbent intact. There is no supplied server implementation and no guarantee of success before the first working submission.

The run has 30 minutes by default, independent of the shared dollar cap. A complete paired benchmark needs time proportional to this level’s workload matrix; budget_status reports the remaining time. Finish may skip optimization when a complete comparison no longer fits. Report this as unoptimized or unmeasured, never maximal performance.
