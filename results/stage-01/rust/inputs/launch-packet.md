# Stage 1: Static files

Contract version: rust-http-v6.

# Shared builder rules

Build a working, efficient HTTP server that satisfies the selected stage's English
contract. Stages 1 and 2 are independent from-scratch assignments. No Rust starter,
previous implementation, or another run's conversation is supplied.

## Freedom to work

You choose the architecture, order of work, debugging strategy, tests and
optimizations. You may use the evaluator tools, supply your own Rust tests, or
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

Submit a complete main.rs through submit_candidate. Compilation and execution
occur in sandboxes. Controller tools are your filesystem/execution interface;
you do not have a general host shell. Additional Rust tests run through run_tests.

You can be stopped at any time. After your first working submission, call
init_repository to create a new private Git repository and its first release tag.
Use release_candidate to publish periodic working milestones. Each numbered tag
contains main.rs and controller-generated release.json evidence. The last completed
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


# Shared executable interface

Submit one UTF-8 file named main.rs, at most 1 MiB, with a Rust executable entry
point. The evaluator uses Rust edition 2021 and optimization level 3. Rust std and
direct libc OS calls through declared FFI are allowed. No Cargo build scripts,
proc macros, downloads, subprocess servers, HTTP frameworks or parser libraries.
The choice of threads, polling, buffers and algorithms is yours. Disclose unsafe
FFI usage. Stage 5 additionally permits system OpenSSL and zlib.

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


# Stage 1: static GET server

Implement GET over HTTP/1.0 and HTTP/1.1 origin-form requests. Respond once and
close with Connection: close. The shared HTTP file-serving requirements apply.
The absolute header deadline starts at accept, including a client that sends no
bytes. Close at header_timeout_ms even if bytes keep arriving. A 408 response is
optional. Concurrency is optional for API acceptance, but performance is evaluated
at 256 and 4096 clients.


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
```

## Supplied smoke checks

These checks demonstrate ordinary API usage only. Design your own tests from the English requirements. Full independent grading is withheld until the run ends.

- `bootstrap`: Ordinary GET of an existing small ASCII file: 200, exact bytes, Content-Length and close.

## Workload matrix

| Workload | Clients | Bytes | Connection |
|---|---:|---:|---|
| fresh-4096-256 | 256 | 4096 | fresh |
| fresh-65536-256 | 256 | 65536 | fresh |
| fresh-4096-4096 | 4096 | 4096 | fresh |
| fresh-65536-4096 | 4096 | 65536 | fresh |
