# Stage 5: TLS and operational features

Contract version: http-v7.

# Shared builder rules

Build a working, efficient HTTP server that satisfies the selected stage's English
contract. Stages 1 and 2 are independent from-scratch assignments. No starter code,
previous implementation, or another run's conversation is supplied.

## Freedom to work

You choose the architecture, order of work, debugging strategy, tests and
optimizations. You may use the evaluator tools, supply your own tests, or
reason about a change before testing it. There is no mandatory iteration sequence,
number of experiments, journal entry, or implementation technique. Tool access,
the source/process interface, sandbox limits and the grading contract still apply.
Testing correctness first, addressing failed requests before speed, and measuring
one change at a time are suggestions. The goal is a working and very efficient
implementation, not compliance with a prescribed development process.

## Testing is part of your task

You are responsible for designing and running tests for your implementation.
Infer what needs testing from the English contract; do not rely on the supplied
checks as a comprehensive test plan. Choose your own cases, tools and strategy.
Providing only enough behavior to pass supplied examples does not satisfy the task.

The English requirements are authoritative. Supplied smoke checks demonstrate
basic API usage only; passing them is not evidence of full correctness. The host
may independently evaluate any behavior required by the contract. It must not
introduce undocumented requirements. No starter implementation is supplied.

Develop and retain your own correctness evidence before publishing releases.
You choose how much capacity to spend on tests versus implementation and
optimization. Report what you tested and any known limitations honestly. Passing
a finite suite does not prove complete correctness or maximum performance.

## Deliverable and Git releases

Submit a complete source file defined by the language interface through submit_candidate. Compilation and execution
occur in sandboxes. Controller tools are your filesystem/execution interface;
you do not have a general host shell. Additional tests run through run_tests.

You can be stopped at any time. After your first working submission, call
init_repository to create a new private Git repository and its first release tag.
Use release_candidate to publish periodic working milestones. Each numbered tag
contains the source file and controller-generated release.json evidence. The last completed
tag is your final submission. Untagged edits do not replace it. No tag means no
submission, and stopping before the first working tag can leave no deliverable.
Published releases must compile, pass bootstrap and preserve previously passing
visible smoke checks. Publication is explicit; submitting source alone does not publish it.

You receive partial credit for validated progress since the previous tag, even
if you do not finish the target. Explain the before/after evidence in each release
note. New passing API checks, demonstrated reliability repairs and valid measured
performance improvements are progress. Duplicate source, cosmetic edits, repeated
claims and extra tags alone earn no additional credit. Do not deliberately split
an easy solution to inflate the milestone count. Numeric milestone weights are
not yet defined.

## Development feedback

submit_candidate and revalidate_candidate run only the supplied smoke suite.
The full host API suite is held out until the run ends. Tool fields named
full_acceptance refer only to the supplied smoke suite, not final correctness.
benchmark_candidate provides provisional ordinary-traffic performance feedback
after smoke acceptance. Such measurements do not establish final eligibility.
Release metadata and retained baselines contain development evidence only.

## Grading

The host grader extracts the last tagged source and compiles it independently.
API correctness is graded first. If compilation or any required API check fails,
performance is not tested and is graded as failed, with zero performance credit.
Failed API checks reduce API credit; the performance credit is also forfeited.
A fast incorrect implementation cannot recover those marks through throughput.

If all API checks pass, the host measures the declared workloads. It reports valid
goodput, latency, failures, timeouts, CPU and memory. Missing or ineligible
measurements earn no demonstrated performance credit. Successful-request latency
must be read alongside failures. A saturated load generator is not evidence of a
server speedup. Reliability, then throughput and latency, are suggested priorities.
The controller's retained comparison baseline is diagnostic; your explicit last
tag determines the final implementation.

## Capacity

The configured campaign cap is $3. The controller reports the actual remaining
shared dollars, tokens and wall time through budget_status and before each model
call. All model input, output, reasoning and final reporting consume that budget.
Compilation and evaluation CPU are tracked separately. The strict worst-case
reservation policy can stop admission well before $3 of settled spend.

Use the available capacity to improve your result. You choose which experiments are worth doing. Continue improving until the
finalization window or admission capacity is exhausted; then use finish. The controller enforces the spending and wall
ceilings regardless of that decision. Do not assume another call will be available
for publication. Record limitations and unmeasured claims honestly in your report.


# Rust build interface

Submit one UTF-8 main.rs, at most 1 MiB, with a Rust executable entry point.
Build: Rust edition 2021, optimization level 3. Rust std and direct libc OS calls
through declared FFI are allowed. No Cargo build scripts, proc macros, downloads,
subprocess servers, HTTP frameworks or parser libraries. Disclose unsafe FFI usage.
Stage 5 additionally permits system OpenSSL and zlib.
run_tests compiles your complete test source using rustc --test.


# Shared executable interface

The selected language document defines the source file, compiler and permitted
libraries. The choice of threads, polling, buffers and algorithms is yours.

The evaluator launches `/candidate/server --config /fixtures/server.conf`.
Read that supplied configuration and bind within two seconds. Configuration is
UTF-8 key=value, one setting per line, with blank lines and # comments allowed.
All keys listed in the stage configuration are required. Reject unknown keys,
duplicates, missing keys and malformed values with a nonzero exit before listening.
Ports are decimal and limits are positive integers unless the stage says otherwise.
Booleans are true or false. Paths are absolute. The root must be an existing
directory; regular files, FIFOs and missing roots are invalid. Values may vary
between independent tests. Do not hardcode the example settings.

The server receives one CPU, 512 MiB address space and at most 16,384 open file
descriptors. Compilation has 4096 MiB address space, 60 CPU seconds and 120 wall
seconds. The candidate executable, fixtures and document root are read-only.
Temporary scratch space is available. Host credentials and other implementations
are absent. Respond on the configured socket; stdout is diagnostic output.


# Shared static-file HTTP requirements

A valid unknown method returns 405. Missing Host is permitted in this restricted profile. Versions other than 1.0 and 1.1 return 400.
Read fragmented requests and require CRLF. Reject bare LF, NUL, invalid header names, folded headers, malformed request lines and malformed headers with 400.
Reject Transfer-Encoding, duplicate Content-Length, invalid lengths and nonzero Content-Length with 400. A single decimal zero, including leading zeroes, is accepted.
Enforce header_bytes including the final CRLFCRLF; excess returns 431.
Strip the query, decode path percent escapes once as UTF-8, reject malformed escapes, fragments, absolute-form, NUL and backslash with 400.
Return 403 for decoded '..' components, symlinks in any component, directories and nonregular files. Missing files return 404. Trailing slash on a regular file returns 403 or 404.
Serve immutable regular files only beneath root. Preserve exact bytes for empty, binary and large files. Explicit Content-Length is mandatory and must match body bytes. No Transfer-Encoding in local responses.
Error bodies may be empty. Successful local responses may use application/octet-stream. Disconnects and malformed clients must not stop later valid service.


# Stage 2: concurrent persistent HTTP

Header field values are opaque bytes and need not be UTF-8; the shared prohibitions on NUL, malformed lines and folded headers still apply.
Support GET and HEAD. For HEAD return the same status and representation headers as GET, including the GET Content-Length, with no body.
HTTP/1.1 persists by default; Connection: close overrides it. HTTP/1.0 closes by default and need not support keep-alive. Include Connection: keep-alive or close explicitly.
Parse Connection tokens case-insensitively. Handle sequential requests and up to pipeline_depth pipelined requests in order. A response body must never be confused with the next header.
Close after max_requests responses, advertising close on the final response. Close idle connections after idle_timeout_ms. An incomplete request has its own absolute header deadline from its first byte; idle waiting uses the idle deadline.
Malformed requests return their error then close. GET and HEAD bodies remain forbidden. Backpressure must bound queued requests and response data; pause reads rather than grow queues beyond pipeline_depth.
Serve concurrent clients independently. Slow input or output on one connection must not block ordinary clients. Enforce max_connections and write_timeout_ms. Refuse or close excess connections without crashing.

The shared HTTP file-serving requirements apply. This is an independent task,
not an extension of a supplied Stage 1 implementation.

Configuration limits are behavioral requirements, not fixed fixture constants.
The evaluator may lower max_connections, pipeline_depth, or write_timeout_ms.
A legal pipeline longer than pipeline_depth must be processed in order using
backpressure, rather than rejected merely because the burst exceeds the queue
bound. Other clients must remain serviceable while that pipeline is blocked.
A write that makes no progress for write_timeout_ms must close the connection
and release its slot. Test with responses larger than socket buffers and clients
that stop reading. Internal queue size cannot be proved by finite black-box tests.


# Shared measurement contract

Each declared workload uses 256 or 4096 active clients and 4 KiB or 64 KiB
responses. Four trusted client workers run five rounds per workload. Each round
has one second of warmup, three seconds of measurement and a two-second request
deadline. There is one outstanding request per client. Persistent workloads do
not benchmark pipelining. Fresh latency includes connection setup; persistent
latency includes reconnecting when required.

Count valid responses only after checking status and exact payload bytes.
Report requests per second, payload bytes per second, p50/p95/p99 successful
request latency, failures, timeouts, round spread, server CPU and peak RSS,
client CPU and event-loop lag. Failures are not silently retried out of the
statistics. These closed-loop workloads do not promise an open-loop arrival rate.
Excess generator lag or saturation makes a measurement inconclusive.

The supplied comparison tool alternates incumbent/challenger rounds. Its
conservative diagnostic promotion requires eligible error-free measurements,
no more than a 5% p99 regression, separated throughput ranges and at least a 5%
geometric-mean throughput gain. You may choose other diagnostic experiments.
The host's final grade uses your tagged source and the declared full matrix.


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
Keep total cached body bytes within cache_bytes and evict entries when necessary. HEAD may use an existing GET entry but must not create an empty GET entry. Expired entries are fetched again; conditional cache revalidation is outside this level's profile.
If gzip=true and Accept-Encoding permits gzip with nonzero quality, gzip local text representations at least 1024 bytes. Include Content-Encoding: gzip and Vary: Accept-Encoding; Content-Length is the compressed size. HEAD uses the same representation headers. Range responses remain uncompressed. Use zlib or an equivalent approved compression library.
When rate_per_second > 0, enforce a global token bucket shared by HTTP and TLS, refilled by monotonic time up to rate_burst. Rejected requests receive 429 and Retry-After. Benchmarks disable this limiter.
On SIGHUP reread the entire configuration atomically. An invalid reload retains the previous configuration. A valid reload changes roots, routing, cache and limiter settings for subsequent requests; flush cache. Listener addresses and TLS paths are immutable across reload and changes to them invalidate reload.
On SIGTERM stop accepting new connections, finish in-flight responses up to drain_timeout_ms, then exit. TLS and plain listeners both drain. Rate limiting, caching and reload must not break path confinement or HTTP framing.

## Required configuration

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

## Supplied smoke checks

These checks demonstrate ordinary API usage only. Design your own tests from the English requirements. Full independent grading is withheld until the run ends.

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
- `headerless-request`: HTTP/1.0 accepts a GET without header fields.
- `head`: HEAD has GET headers and length with no body, including missing files.
- `persistent-pipeline`: Persistent and pipelined responses retain order and exact framing.
- `connection-semantics`: HTTP/1.0 defaults to close; mixed-case Connection tokens override HTTP/1.1 persistence.
- `connection-limits`: Close after 100 requests; close idle persistent connections after two seconds.
- `slow-client-fairness`: A slow sender and a stalled large-file reader do not block ordinary requests.
- `byte-header-values`: Opaque header values need not be UTF-8.
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
- `connection-capacity`: A small configured connection limit rejects excess clients and recovers after disconnects.
- `write-deadline`: A blocked writer releases its connection slot after the configured write deadline.
- `pipeline-backpressure`: A burst beyond pipeline_depth retains ordered responses and does not block another client.
- `configuration`: Invalid, duplicate, missing and unknown config values exit nonzero before serving.

## Workload matrix

| Workload | Clients | Bytes | Connection |
|---|---:|---:|---|
| fresh-4096-256 | 256 | 4096 | fresh |
| fresh-65536-256 | 256 | 65536 | fresh |
| persistent-4096-256 | 256 | 4096 | persistent |
| persistent-65536-256 | 256 | 65536 | persistent |
| proxy-4096-256 | 256 | 4096 | persistent |
| proxy-65536-256 | 256 | 65536 | persistent |
| tls-4096-256 | 256 | 4096 | persistent |
| tls-65536-256 | 256 | 65536 | persistent |
| gzip-4096-256 | 256 | 4096 | persistent |
| gzip-65536-256 | 256 | 65536 | persistent |
| fresh-4096-4096 | 4096 | 4096 | fresh |
| fresh-65536-4096 | 4096 | 65536 | fresh |
| persistent-4096-4096 | 4096 | 4096 | persistent |
| persistent-65536-4096 | 4096 | 65536 | persistent |
| proxy-4096-4096 | 4096 | 4096 | persistent |
| proxy-65536-4096 | 4096 | 65536 | persistent |
| tls-4096-4096 | 4096 | 4096 | persistent |
| tls-65536-4096 | 4096 | 65536 | persistent |
| gzip-4096-4096 | 4096 | 4096 | persistent |
| gzip-65536-4096 | 4096 | 65536 | persistent |
