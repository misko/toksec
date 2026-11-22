# Stage 14: Fair admission

# Shared builder rules

Build a working, secure and efficient HTTP server that satisfies the selected stage's English
contract. Each selected stage is an independent from-scratch assignment. No starter code,
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

## Secure defaults and testing

Enable only the listeners, transports and protocol versions specified for the
stage and enabled by its configuration. A plaintext HTTP stage must still serve
plaintext HTTP. Where TLS is required, enforce the specified versions and peer
checks. Reject unsupported negotiation instead of falling back to plaintext or
a weaker protocol. Keep these protections active during benchmarks.

Design tests for the security boundaries your stage implements. Pair a request
that should succeed with one that should be refused, and check the observable
effect as well as the response. For example, a request denied by a proxy should
never reach its upstream, and a failed handshake on a TLS listener should never
deliver application data. Choose cases appropriate to your stage and record what
you verified and any remaining gaps in your release notes.

## Deliverable and Git releases

Submit a complete source file defined by the supplied `artifact.json` and language interface through submit_candidate.
The shared artifact instructions define ownership of source, release metadata and parent evaluation files. Compilation and execution
occur in sandboxes. Controller tools are your filesystem and execution interface.
Use run_tests for standalone tests. When run_candidate_test is supplied, your
test client can send requests to the selected, running server. Select its
source_sha256. The driver starts the compiled server with the stage's public
configuration and files. Your test may provide its own upstream listeners.

You can be stopped at any time. After your first working submission, call
init_repository to create a new private Git repository and its first release tag.
If submit_candidate accepts release_note, supplying a note also requests a tag
for that submission and creates the private Git repository when needed. Use
release_candidate to publish periodic working milestones. Each numbered tag
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

submit_candidate and, when available, revalidate_candidate run only the supplied smoke suite.
Independent host API checks are held out until the run ends. The smoke_passed field refers only to the supplied smoke suite, not final correctness.
benchmark_candidate provides provisional ordinary-traffic performance feedback
after smoke acceptance. Such measurements do not establish final eligibility.
Release metadata and retained baselines contain development evidence only.
The selected stage declares whether independent API coverage is full or partial.
Passing all available checks in a partial suite cannot establish full acceptance.
Any performance diagnostics for such a stage remain provisional and earn no final
performance credit. Use only the tools actually supplied for the selected stage.

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

The frozen run manifest defines the campaign cap and builder wall-time ceiling. The controller reports the actual remaining
shared dollars, tokens and wall time through budget_status and before each model
call. All model input, output, reasoning and final reporting consume that budget.
Compilation and evaluation CPU are tracked separately. The strict worst-case
reservation policy can stop admission before the authorized balance is fully spent.

After you have a working tag, choose a remaining correctness risk or a bottleneck
you can measure. Test a change against the tagged version. Tag demonstrated
progress and retain your working tag when an experiment fails. Each model turn
includes capacity feedback. On stages with candidate client tests, it also gives
your current source hash, last tag and latest benchmark decision.
You choose which experiments are worth doing. Continue improving until the
finalization window or admission capacity is exhausted; then use finish. The controller enforces the spending and wall
ceilings regardless of that decision. Do not assume another call will be available
for publication. Record limitations and unmeasured claims honestly in your report.


# C++ build interface

Submit one UTF-8 main.cpp, at most 1 MiB, containing int main(int argc, char** argv).
The evaluator compiles with g++ -std=c++20 -O3 -DNDEBUG -pthread. No build system,
additional source files, downloaded dependencies or custom compiler/linker flags.

Use only the C++ standard library, C standard library and POSIX/Linux OS APIs
such as sockets, epoll/poll, threads, filesystem operations and sendfile.
No third-party libraries, HTTP parsers/frameworks, Boost, networking libraries,
TLS/encryption/cryptography or compression libraries. Do not load libraries at
runtime or delegate to subprocess programs. All five stages serve plaintext HTTP;
there is no encryption requirement and you should not implement cryptography.
The compile harness checks included header provenance and linked dependencies.

Submit a complete C++ test program with its own main() to either test tool.
The compiler enables assertions. Exit zero for success and nonzero for failure.
run_tests executes that program with its own build directory. run_candidate_test starts
your selected server, then executes the program in a separate sandbox on its
private network. Send HTTP requests to 127.0.0.1:8080. The server uses the
normal stage configuration and public files. The client supplies any upstreams
its test needs. Read the returned build result and the test process exit code.
You choose your implementation, debugging and testing methods.


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


# Artifact ownership and submission format

The supplied `artifact.json` defines your source filename, UTF-8 encoding, size
limit, and release-tag format. Submit the complete source through
`submit_candidate`. The controller validates the contract and writes the required
filename. Do not choose a different submission path or create parent-owned files.

The controller owns `release.json` and creates numbered Git tags when you call
`init_repository` or `release_candidate`. On stages with an optional
`release_note` argument, a submission or edit can request a tag in the same call.
Only the last completed tag is the final
submission. Untagged changes and claims in a report do not replace that tag.

The parent publishes the frozen implementation separately from independent API
results, performance measurements, reports, and figures. You do not write the
parent's evaluation files or choose their destination. Development smoke feedback
and your own tests are not parent acceptance evidence.


# Shared static-file HTTP requirements

A valid unknown method returns 405. Missing Host is permitted in Stages 1–2; Stages 3–5 use the routing Host requirements. Versions other than 1.0 and 1.1 return 400.
Read fragmented requests and require CRLF. Reject bare LF, NUL, invalid header names, folded headers, malformed request lines and malformed headers with 400.
On local file routes, reject Transfer-Encoding, duplicate Content-Length, invalid lengths and nonzero Content-Length with 400. A single decimal zero, including leading zeroes, is accepted.
Enforce header_bytes including the final CRLFCRLF; excess returns 431.
Strip the query, decode path percent escapes once as UTF-8, reject malformed escapes, fragments, absolute-form, NUL and backslash with 400.
Return 403 for decoded '..' components, symlinks in any component and nonregular files. Stages 1–2 reject directories with 403; Stages 3–5 use the routing index/redirect rules. Missing files return 404. Trailing slash on a regular file returns 403 or 404.
Local file routes serve immutable regular files beneath the selected root or alias. Preserve exact bytes for empty, binary and large files. Explicit Content-Length is mandatory and must match body bytes. No Transfer-Encoding in local responses.
Error bodies may be empty. Successful local responses may use application/octet-stream. Disconnects and malformed clients must not stop later valid service.


# Persistent HTTP

Header field values are opaque bytes and need not be UTF-8; the shared prohibitions on NUL, malformed lines and folded headers still apply.
Support GET and HEAD. For HEAD return the same status and representation headers as GET, including the GET Content-Length, with no body.
HTTP/1.1 persists by default; Connection: close overrides it. HTTP/1.0 closes by default and need not support keep-alive. Include Connection: keep-alive or close explicitly.
Parse Connection tokens case-insensitively. Handle sequential requests and up to pipeline_depth pipelined requests in order. A response body must never be confused with the next header.
Close after max_requests responses, advertising close on the final response. Close idle connections after idle_timeout_ms. An incomplete request has its own absolute header deadline from its first byte; idle waiting uses the idle deadline.
Malformed requests return their error then close. Local GET and HEAD bodies remain forbidden. Backpressure must bound queued requests and response data; pause reads rather than grow queues beyond pipeline_depth.
Serve concurrent clients independently. Slow input or output on one connection must not block ordinary clients. Enforce max_connections and write_timeout_ms. Refuse or close excess connections without crashing.



# Shared gateway API

Use Stage 2 static-file and connection behavior, including 403 for directories. On gateway requests require one Host. GET and HEAD /gateway/<path> go to the configured origin_address, removing /gateway and preserving the query and Host. Relay the origin status and exact body with Content-Length. Local routes never depend on an upstream. Use HTTP/1.1 with Content-Length upstream; no chunked coding is required. Distinguish local filesystem routing from upstream URI handling. Do not emit hop-by-hop or client-controlled connection headers to the origin. A failed origin returns 502. Gateway benchmarks use /gateway/data/{size}, except admission additionally uses the public route /data/{size} to measure unaffected service and upload uses POST /gateway/upload with the workload bytes echoed by the origin. A 429 is never a successful-service sample. All servers start with an empty workspace.


# Admission

Rate-limit /gateway/ using two initially full token buckets: per effective client and global, with capacities client_burst and global_burst respectively. Each refills one token per refill_ms up to capacity. Accept only if both have a token and debit both atomically. Otherwise return 429 without contacting the origin. Use the TCP peer address, except that a peer equal to trusted_peer may supply one valid IPv4 X-Real-IP. Ignore that header from other peers. GET /health always returns 200 with body ok plus newline and consumes no tokens. SIGHUP installs valid configuration atomically and resets buckets; invalid replacements preserve service.


# Stage 14: Fair admission

Independent from-scratch assignment. Rate-limit /gateway/ using two initially full token buckets: per effective client and global, with capacities client_burst and global_burst respectively.


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


Stage 3 adds persistent routed files from beta.test via the alias prefix, using
the same payload sizes. Stage 4 adds persistent proxy GETs to healthy upstreams.
Proxy/operations runs require a sixth CPU dedicated to the trusted upstreams,
separate from the server and four generators. Upstream utilization above 90%
makes the measurement ineligible. These resources are reported in each round.

Stage 5 adds cache-hit and cache-miss workloads. Benchmark configuration sets
cache_ttl_ms=60000, cache_bytes=4194304 and rate_per_second=0. A cache-hit round
repeats one URL whose upstream sends public,max-age=60; the one-second warmup
primes it before measurement. A cache-miss round repeats a URL with max-age=0,
so responses must not be reused. Both return the ordinary 4/64-KiB payloads.
No TLS or gzip is measured in the bare-bones operations profile.

benchmark_candidate accepts a declared workload ID for a smaller diagnostic run,
or null for the full matrix. Subset measurements do not promote a full-matrix
baseline. Every result identifies its selected workloads. Final grading still
requires full API acceptance followed by the complete declared matrix.

For Stages 11–16 the parent also checks the declared downstream effects. Origin
and authorization counters include warmup. Protected responses require a fresh
decision each time. Caching workloads must demonstrate reuse. Refusals and
timeouts cannot earn successful delivery throughput. The mixed state and quota
checks run in the API gate. Stage 14 measures local service and admitted gateway service separately, with
both burst limits set to ten million during performance rounds. Cache performance uses a 60-second TTL and uploads use 256 MiB aggregate
and tenant quotas and a two-second upload deadline during load measurement.


## Artifact contract

```json
{
  "language": "cpp",
  "release": {
    "metadata_owner": "controller",
    "selection": "last_completed_tag",
    "tag_pattern": "^release/[0-9]{6}$"
  },
  "schema_version": 1,
  "stage": 14,
  "submission": {
    "encoding": "utf-8",
    "max_bytes": 1048576,
    "source_file": "main.cpp"
  }
}
```

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
origin_address=127.0.0.1:8081
client_burst=3
global_burst=8
refill_ms=1000
trusted_peer=127.0.0.1
```

## Supplied smoke checks

These checks demonstrate ordinary API usage only. Design your own tests from the English requirements. Full independent grading is withheld until the run ends.

- `bootstrap`: Ordinary GET of an existing small ASCII file: 200, exact bytes, Content-Length and close.
- `smoke-head`: Ordinary HEAD of the same existing file: 200, representation length and no body.
- `smoke-persistent`: Two ordinary sequential GETs on one persistent connection.

## Workload matrix

| Workload | Clients | Bytes | Connection |
|---|---:|---:|---|
| gateway-14-public-4096-256 | 256 | 4096 | persistent |
| gateway-14-public-65536-256 | 256 | 65536 | persistent |
| gateway-14-admitted-4096-256 | 256 | 4096 | persistent |
| gateway-14-admitted-65536-256 | 256 | 65536 | persistent |
| gateway-14-public-4096-4096 | 4096 | 4096 | persistent |
| gateway-14-public-65536-4096 | 4096 | 65536 | persistent |
| gateway-14-admitted-4096-4096 | 4096 | 4096 | persistent |
| gateway-14-admitted-65536-4096 | 4096 | 65536 | persistent |
