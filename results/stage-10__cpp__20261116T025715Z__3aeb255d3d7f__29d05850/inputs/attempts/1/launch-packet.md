# Stage 10 implementation assignment



# Shared builder rules

Build a working, efficient HTTP server that satisfies the selected stage's English
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

## Deliverable and Git releases

Submit a complete source file defined by the supplied `artifact.json` and language interface through submit_candidate.
The shared artifact instructions define ownership of source, release metadata and parent evaluation files. Compilation and execution
occur in sandboxes. Controller tools are your filesystem/execution interface;
you do not have a general host shell. Additional tests run through run_tests. Your test programs must set up their own
fixtures and listeners; no candidate server is automatically running for them.

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

Use the available capacity to improve your result. You choose which experiments are worth doing. Continue improving until the
finalization window or admission capacity is exhausted; then use finish. The controller enforces the spending and wall
ceilings regardless of that decision. Do not assume another call will be available
for publication. Record limitations and unmeasured claims honestly in your report.


# Artifact ownership and submission format

The supplied `artifact.json` defines your source filename, UTF-8 encoding, size
limit, and release-tag format. Submit the complete source through
`submit_candidate`. The controller validates the contract and writes the required
filename. Do not choose a different submission path or create parent-owned files.

The controller owns `release.json` and creates numbered Git tags when you call
`init_repository` or `release_candidate`. Only the last completed tag is the final
submission. Untagged changes and claims in a report do not replace that tag.

The parent publishes the frozen implementation separately from independent API
results, performance measurements, reports, and figures. You do not write the
parent's evaluation files or choose their destination. Development smoke feedback
and your own tests are not parent acceptance evidence.


# Stage 10: HTTP/HTTPS server with worker lifecycle

Packet status: draft, not launchable. The host must remove this restriction only
after the readiness gates in its evaluation plan pass. This packet contains no
starter implementation. Do not treat example configuration as the only input.

Implement a working, efficient HTTP/1.1 server from scratch in the language named
by the run manifest. Read RULES.md first, then INTERFACE.md, your language policy,
HTTP.md, CONFIGURATION.md, TLS.md, OPERATIONS.md and BENCHMARK.md. SMOKE.md describes
the small visible checks. Together these files define this assignment; no earlier
stage packet or implementation is required.

The deliverable serves static files and proxies plaintext upstreams over HTTP and
HTTPS downstream connections. It parses the supported nginx configuration subset,
streams bodies, coordinates cache refreshes, bounds admission and replaces failed
workers. Implement the complete specified subset, not full nginx compatibility.

You choose architecture, testing, debugging and optimization. You may be stopped
at any time. Publish a working first tag as soon as possible, then periodic tags
with evidence of progress. The last completed tag is the final artifact. No tag
means no submitted implementation. The host grades the complete API first; any
required API failure prevents final performance credit.

A sensible optional sequence is plaintext GET, configuration selection, HTTPS,
proxy streaming, cache coordination and worker recovery. This sequence is advice,
not a required implementation plan. Do not postpone all working releases until
the complete Stage 10 target is implemented. Smoke results are not full acceptance.

Use capacity feedback to preserve a working release and improve correctness and
performance while budget remains. Explain known limitations honestly. Source code
and release notes must never contain host credentials or production TLS keys.


# Source, process and fixture interface

Submit one UTF-8 main.cpp or main.rs, at most 1 MiB, through submit_candidate.
The controller compiles and runs it in a sandbox. No additional implementation
files, downloaded dependencies, HTTP libraries or previous implementations are
provided. Approved OpenSSL is the sole TLS dependency exception. See your language
policy and TLS.md. Compiler and library identities belong in the run manifest.

Launch the master as `/candidate/server --config /fixtures/config/nginx.conf`.
`--check-config PATH` validates configuration, includes, roots and TLS material,
prints a diagnostic on failure, and exits without binding or forking workers.
Exit zero means valid; a nonzero exit means invalid. Diagnostics identify file
and line where possible and never print private key contents.

Initial startup must make all configured listeners serviceable within five seconds.
The master remains foreground; do not daemonize. SIGTERM to the master starts a
bounded graceful drain. SIGHUP requests transactional configuration/certificate
reload. OPERATIONS.md defines worker replacement and generation semantics.

The host mounts these fixture paths in each test sandbox:

| Path | Access and use |
|---|---|
| /fixtures/config | Read-only to candidate; host may replace files for reload tests |
| /fixtures/tls | Read-only test-only certificate chains, leaf private keys and CA certificate |
| /www | Read-only immutable files, with alternate roots and aliases in tests |
| /tmp | Private writable scratch, capped at 64 MiB by the host |
| /candidate | Read-only source snapshot and executable |

The supplied sample files demonstrate inputs. Host fixtures vary names, content,
ports and limits within the contract. Do not hardcode sample values. No host
credentials, CA signing private key, reference server or hidden checker is mounted.
Upstream fixture services are reachable only in the sandbox's private network.

The process tree receives 1, 2 or 4 CPUs as declared in each measurement profile,
512 MiB aggregate charged memory, 16,384 total live file descriptors, and at most
one master plus four worker processes. The host includes mapped OpenSSL and
charged scratch/cache memory in the resource budget; it must publish the exact
memory-accounting method. Do not interpret per-process limits as separate budgets.
Compile limits remain 4096 MiB address space, 60 CPU seconds and 120 wall seconds.
Aggregate enforcement must pass host preflight before any run is authorized.

The source may fork workers from itself but may not execute external programs or
delegate HTTP/TLS/configuration parsing to another executable. IPC, shared memory,
threads, POSIX/Linux I/O and the approved TLS C ABI are allowed. Worker thread
counts and descriptors remain inside the aggregate resource budget.

Controller tools retain their existing names: budget_status, submit_candidate,
revalidate_candidate, run_tests, benchmark_candidate, init_repository,
release_candidate and finish. Tests are your own standalone programs run in the
same isolation policy. They must create their own listeners and fixtures.
The controller owns compilation, Git initialization/tagging and release evidence.
These tool names describe the intended Stage 10 interface, not current support.


# C++ policy

Submit main.cpp containing int main(int argc, char** argv). The proposed build is:

```sh
g++ -std=c++20 -O3 -DNDEBUG -pthread main.cpp -o server -lssl -lcrypto
```

Use the C++/C standard libraries, POSIX/Linux APIs and the pinned OpenSSL headers
and libssl/libcrypto. No Boost, HTTP parsers/frameworks, other networking, crypto
or compression libraries, runtime library loading or external helper programs.
The host validates header provenance and linked dependencies. Standard toolchain
runtime dependencies are allowed as recorded in the build manifest.

Use OpenSSL for TLS and cryptography; implement HTTP and configuration yourself.
run_tests compiles a standalone test program without -DNDEBUG, with the same
approved dependencies. No test framework or server source is supplied.


# HTTP behavior

This is the complete Stage 10 HTTP subset. CONFIGURATION.md defines routing and
limit names; TLS.md changes transport, not application response semantics.

## Parsing and persistent connections

Accept HTTP/1.0 and HTTP/1.1 with CRLF framing and fragmented input. Reject other
versions, malformed request lines, bare LF, folded headers, NUL, invalid token
header names and prohibited control bytes in values with 400 then close. Header
values otherwise remain opaque bytes. An unknown syntactically valid method
returns 405. Support GET/HEAD locally and GET/HEAD/POST on proxy locations.
Requests containing Expect return 417 and close before forwarding a body;
Expect/100-continue negotiation is outside this subset.

HTTP/1.1 requires exactly one valid Host. HTTP/1.0 without Host uses the listener's
default virtual server. CONFIGURATION.md defines host normalization and unmatched
host behavior. Do not confuse SNI certificate selection with HTTP routing.

HTTP/1.1 is persistent unless Connection: close is present. HTTP/1.0 closes after
each response. Include an explicit Connection field. Parse its tokens without case
sensitivity. Serve sequential and pipelined requests in order. Pause input at the
configured pipeline limit rather than growing an unbounded request queue. Close
after keepalive_requests responses and advertise close on the final response.

Enforce absolute header and idle/write deadlines as specified in CONFIGURATION.md.
Header-size excess returns 431 then closes. A silent or stalled client cannot
prevent other clients progressing. Excess connections may be refused or closed.
Malformed clients and disconnects must not stop subsequent ordinary service.

## Local files

Split the query before decoding the path once as UTF-8. Reject malformed escapes,
invalid UTF-8, fragments, absolute-form targets, NUL and backslash with 400. Reject
decoded '..' components, any symlink component and nonregular files with 403.
Collapse repeated slashes and '.' components after decoding, before location selection.
Serve only immutable regular files confined beneath the selected root or alias.
Missing files return 404. A slash after a regular filename returns 403 or 404.

Reject local Transfer-Encoding, duplicate Content-Length, invalid lengths and
nonzero Content-Length with 400. A single decimal zero is accepted. Serve exact
bytes, including binary, empty and large files, with Content-Length and no
Transfer-Encoding. HEAD has GET's status and representation headers but no body.
Error bodies may be empty. MIME selection follows the configured types/default.

Directories without slash redirect with 301 and preserve the query. A trailing
slash selects the configured index if it is a regular file; otherwise return 403.
When etag is on, emit a stable quoted ETag. Matching If-None-Match or '*' returns 304 with ETag,
Content-Length: 0 and no body. With etag off, omit ETag and ignore If-None-Match. Check conditional handling before Range. Support a single bytes
range N-M, N- or -N on GET/HEAD; clamp the end to EOF. Return 206 and Content-Range
for satisfiable ranges, 416 with bytes */SIZE for unsatisfiable ranges, and 400 for
malformed or multiple ranges. All operations use the selected representation.

## Proxy framing and streaming

CONFIGURATION.md defines proxy_pass target construction and upstream selection.
Accept one Content-Length or one Transfer-Encoding: chunked, never both. Reject
duplicate lengths, unsupported transfer codings, malformed chunks or ambiguous
framing with 400. Decoded request bodies above the configured body limit return
413 before response commitment; close if a response is already committed.
Bound and validate trailers using the configured header limit; do not forward them.

Strip standard hop-by-hop fields and fields named by Connection in both
directions. Rewrite upstream Host to the chosen numeric endpoint authority.
Preserve end-to-end fields, status and exact decoded body. Reject malformed or
ambiguous upstream framing with 502 before commitment. Recognize Content-Length,
chunked and EOF-delimited upstream responses. HEAD never sends downstream body.
Discard at most eight informational 1xx responses before the final response;
101 switching protocols or excess informational responses produce 502. Apply the
header limit and upstream deadline while reading these responses. Final 204 and
304 responses have no body regardless of connection persistence. Omit framing
fields on 204. A valid Content-Length on 304 or HEAD describes representation
length only; never read that many body bytes. Never emit chunked framing on these
bodyless responses. A revalidation 304 is consumed by the cache logic in
OPERATIONS.md; otherwise forward 304 without body. Incompatible framing or
unsolicited bytes must not contaminate a later response.

Forward request/response body progress before the sender finishes. For known
lengths preserve Content-Length; for unknown lengths emit chunked HTTP/1.1 or
close-delimited HTTP/1.0. Never emit both Content-Length and Transfer-Encoding.
This explicitly replaces Stage 5's always-buffer-to-known-length proxy behavior.
Content-Length is still mandatory on local file responses.

On truncation, malformed framing, size excess or deadline after downstream headers
are committed, close without a successful chunk terminator or a second response.
Before commitment return 502 for upstream transport/framing failures and 504 for
upstream deadlines. Invalidate the failed upstream connection. Never return a
connection with unread body bytes to its reuse pool.

In a functional progress test, an upstream sends headers and a 64 KiB body prefix,
then waits for the client to acknowledge that prefix before sending the remainder.
The proxy must deliver the prefix within one second on an otherwise idle host.
Apply the equivalent test to uploads. Slow-reader tests verify bounded resource
usage and simultaneous small-request service; buffering whole large bodies is
not an acceptable streaming implementation.

Use bounded FIFO upstream admission and connection reuse. A full waiting queue
rejects new requests with 503 and Retry-After: 1. Queued requests expire at the
configured queue deadline with the same response. New arrivals/retries must not
overtake existing eligible waiters for the same upstream group. Do not retry POST.
Bodyless GET/HEAD may retry once on the next endpoint before downstream commitment.
Bound attempts to two total and preserve the original queue/attempt accounting.
Failures/cancellation release slots and cannot poison unrelated routes.


# Stage 10 configuration contract

Status: proposed builder reference. This packet is not runnable or published.
This file defines a restricted nginx configuration language and Toksec extensions.
It does not require full nginx compatibility. HTTP behavior is defined by `HTTP.md`.
TLS behavior is defined by `TLS.md`. Process and resource limits are defined by `INTERFACE.md`.

## Input and grammar

The entry point is `server --config /fixtures/config/nginx.conf`.
`server --check-config /fixtures/config/nginx.conf` performs the same complete validation without binding sockets or starting workers.
Success exits 0. Invalid input exits nonzero and reports the source file and one-based line to stderr without key contents.
Initial validation finishes before accepting connections. The implementation parses the configuration itself.

```text
configuration := statement*
statement     := word argument* ";" | word argument* "{" statement* "}"
argument      := bare | single_quoted | double_quoted
```

Input is UTF-8 without NUL or BOM. Keywords and enumerated values are case-sensitive ASCII.
Whitespace is space, tab, CR, or LF. A CRLF counts as one line and a lone CR is whitespace.
Outside quotes, `#` starts a comment through the next LF. `;`, `{`, and `}` are separate tokens.
A bare argument ends at whitespace, a delimiter, or `#`. Quotes must surround the whole argument.
Both quote forms permit whitespace, delimiters, and `#` literally, but prohibit raw CR and LF.
In all argument forms, backslash escapes backslash, either quote, space, tab, `#`, `;`, `{`, or `}` to that character.
The sequences `\n`, `\r`, and `\t` decode to LF, CR, and tab. Other escapes, dangling escapes, and unfinished quotes fail.
Decoded control characters are rejected by directive value grammars unless explicitly allowed. No directive below permits them in paths or names.
There is no variable substitution, environment expansion, quote concatenation, or shell execution. An argument containing `$` fails.
These lexical restrictions deliberately reject forms beyond this subset.

The expanded input has at most 1 MiB of source bytes, 16,384 statements, 4,096 bytes per decoded argument, and 32 arguments per statement.
At most 128 files may be opened per parse, counting repeated inclusions. Block depth is at most 8 and include depth at most 8 beyond the entry file.
All numeric values are unsigned decimal without sign, fraction, whitespace, or overflow.
`N` means 1 through 2^31-1. `Z` additionally permits zero. Directive-specific bounds override these ranges.
`SIZE` is `Z` optionally followed by `k` or `m`, multiplying by 1024 or 1048576, with a maximum of 2^31-1 bytes.
`TIME` is `N` optionally followed by `ms` or `s`. No suffix means seconds. The converted value must be at most 86,400,000 ms.

## Includes and contexts

`include PATH;` takes exactly one argument, is repeatable in every context, and expands statements in place.
Relative include paths resolve against the directory containing the entry configuration, never the including file's directory.
Absolute include paths must remain in that same configuration tree. Symlinks, `..` components, and nonregular files fail.
The only glob is `*`, matching zero or more filename bytes within the final path component, never `/` or a leading dot.
Matches expand in ascending UTF-8 byte order. A missing literal file fails. A glob with zero matches inserts no statements.
An include cycle on the active expansion stack fails. Repeated acyclic includes are parsed again and obey ordinary duplicate rules.
Included text inherits the caller's context and must contain complete statements. Blocks cannot cross file boundaries.

Contexts below are `M` main, `E` events, `H` http, `U` upstream, `S` server, and `L` location.
There must be exactly one `events {}` and one `http {}` in main, each with zero arguments.
`http` contains one or more `server {}` blocks and zero or more `upstream NAME {}` blocks.
Server blocks take zero arguments. Upstream names match `[A-Za-z_][A-Za-z0-9_]*` and must be unique.
`location PATH {}` and `location = PATH {}` occur only in server blocks. Nested locations are excluded.
Location paths start with `/`, contain no query, fragment, percent escapes, duplicate slash, `.` or `..` component, and are case-sensitive UTF-8.
One exact and one prefix location may share a path. Duplicate locations of the same kind fail.
Every server must declare a prefix `location /` as its fallback.
`types {}` is a zero-argument special mapping block permitted in H, S, and L.

## Native directive subset

Except where marked repeatable, each directive occurs at most once in its immediate context.
For directives permitted in H, S, and L, a child inherits its parent's value when absent and otherwise replaces it.
Other directives do not inherit unless stated. Every table row lists the complete accepted argument form.
Defaults apply after inheritance. The packet deliberately narrows accepted values, contexts, and optional parameters.

| Directive and arguments | Context | Default and meaning |
|---|---|---|
| `worker_processes 1\|2\|4` | M | `1`. Worker count, excluding the master. Immutable on reload. |
| `worker_connections N` | E | `512`. Per-worker active downstream plus upstream connections, including TLS handshakes and idle connections. |
| `listen 127.0.0.1:PORT [ssl] [default_server]` | S | Required, repeatable for distinct endpoints. PORT is 1..65535. Optional flags occur at most once in this order. |
| `server_name NAME...` | S | Required, 1..32 names. ASCII DNS labels, case-insensitive, no wildcard, regex, trailing dot, or underscore. |
| `root PATH` | H,S,L | `html` relative to the configuration prefix. Appends the complete normalized request path to this directory. |
| `alias PATH` | L | Absent. Only prefix locations ending in `/`, with an absolute directory PATH ending in `/`. Replaces the matched location prefix. |
| `index NAME...` | H,S,L | `index.html`. 1..32 plain filenames without slash, backslash, `.` or `..`. Try in order. |
| `default_type TYPE` | H,S,L | `text/plain`. TYPE is an ASCII media type `token/token` without parameters. |
| `etag on\|off` | H,S,L | `on`. Enables local representation ETags and conditional handling in HTTP.md. |
| `return 301\|302\|307\|308 DESTINATION` | L | Absent. Literal nonempty URI beginning `/`, `http://`, or `https://`, without whitespace or controls. |
| `keepalive_timeout TIME` | H,S,L | `75s`. Idle persistent downstream connection timeout. Also accepts literal `0` to disable persistence. |
| `keepalive_requests N` | H,S,L | `1000`. Maximum requests on one downstream connection. |
| `client_header_timeout TIME` | H,S | `60s`. Time allowed to receive the complete request header. |
| `client_body_timeout TIME` | H,S,L | `60s`. Maximum gap between downstream body reads. |
| `send_timeout TIME` | H,S,L | `60s`. Maximum gap between successful downstream writes. |
| `client_max_body_size SIZE` | H,S,L | `1m`. Maximum decoded request body. Zero removes this directive's cap; the Toksec body cap still applies. |
| `server 127.0.0.1:PORT` | U | Required, repeatable, distinct endpoints. At least one endpoint, at most 16. Equal-weight round robin. |
| `keepalive N` | U | No idle pool when absent. Maximum idle upstream connections per worker for this group, not an active-connection cap. |
| `proxy_pass http://NAME[/URI]` | L | Absent. NAME must name an upstream block. Literal URI starts `/` and contains no query, fragment, percent escapes, or variables. |
| `proxy_connect_timeout TIME` | H,S,L | `60s`. Connection-establishment deadline. |
| `proxy_read_timeout TIME` | H,S,L | `60s`. Maximum gap between upstream reads. |
| `proxy_send_timeout TIME` | H,S,L | `60s`. Maximum gap between upstream writes. |

`types` entries are `TYPE EXTENSION...;`, with 1..32 nonempty ASCII alphanumeric extensions per entry.
Extension matching is case-insensitive. Duplicate extensions in one mapping fail.
An absent block inherits the whole parent mapping. A present block replaces it, including an empty block.
The initial mapping is `text/html html; image/gif gif; image/jpeg jpg;`. Fixtures explicitly add `text/plain txt;`.
File paths resolve against the entry configuration directory when relative and must remain within supplied fixture or document roots.
`alias` and a local `root` cannot coexist. An alias overrides an inherited root. `return`, `proxy_pass`, and `alias` are mutually exclusive in one location.
A return or proxy location may inherit a root but does not serve files. Native directives omitted from this table or TLS.md fail explicitly.

An exact location wins. Otherwise the longest matching prefix wins. HTTP.md defines path normalization and confinement before matching.
An upstream URI on `proxy_pass` replaces the matched normalized location prefix, preserving the request query.
For example, `/api/a?x=1` under `location /api/` with `proxy_pass http://backend/;` becomes `/a?x=1`.
Without an upstream URI, the original request target is forwarded unchanged for accepted requests. Exact locations may also use URI replacement.
Return destinations are emitted literally without variable expansion or implicit query append. Directory redirects follow HTTP.md separately.
This target's strict Host validation and HTTP safety rules are separate from nginx compatibility.

## Toksec extension directives

Each extension takes one argument, occurs once in H only, has no inheritance, and applies across all workers and listeners unless stated.
Timers use monotonic time. These controls preserve benchmark semantics without assigning new meanings to nginx cache or rate directives.

| Directive | Grammar | Default and scope |
|---|---|---|
| `toksec_header_bytes` | SIZE, nonzero | `16k`. Complete request header limit. |
| `toksec_pipeline_depth` | N, at most 64 | `8`. Maximum outstanding requests per downstream connection. |
| `toksec_max_connections` | N | `8192`. Aggregate downstream connections, including handshakes. |
| `toksec_body_bytes` | SIZE, nonzero | `64m`. Decoded request and response body ceiling. |
| `toksec_header_deadline` | TIME | `2s`. Absolute deadline from first request byte. |
| `toksec_write_deadline` | TIME | `10s`. Absolute response deadline from first attempted downstream write. |
| `toksec_upstream_deadline` | TIME | `10s`. Absolute deadline across admission, all attempts, and response completion. |
| `toksec_upstream_active` | N | `256`. Aggregate active requests per upstream group. |
| `toksec_upstream_queue` | Z | `256`. Aggregate waiting requests per upstream group. |
| `toksec_upstream_queue_timeout` | TIME | `2s`. Absolute time in upstream admission queue. Expiry returns 503. |
| `toksec_cache_bytes` | SIZE | `32m`. Aggregate cached body bytes. Zero disables cache. |
| `toksec_cache_entries` | N | `4096`. Aggregate entry ceiling, partitioned equally among workers. |
| `toksec_cache_waiters` | N | `256`. Maximum waiting clients per cache key per worker. Excess returns 503 with Retry-After: 1. |
| `toksec_upstream_failures` | N | `3`. Consecutive transport/deadline failures before endpoint cooldown, across workers. |
| `toksec_upstream_cooldown` | TIME | `1s`. Endpoint exclusion interval, followed by one global probe. |
| `toksec_cache_ttl` | TIME | `5s`. Freshness lifetime ceiling. |
| `toksec_rate_per_second` | Z | `0`. Aggregate token refill rate. Zero disables rate limiting. |
| `toksec_rate_burst` | N | `100`. Aggregate token bucket capacity. |
| `toksec_drain_timeout` | TIME | `5s`. Maximum graceful shutdown duration. |
| `toksec_tls_handshake_timeout` | TIME | `2s`. Absolute deadline from accept through TLS handshake completion. |

When several deadlines apply, the earliest expiration wins. HTTP.md defines errors, retry, streaming, cache, and admission behavior.
The limiter bucket starts full. Each request consumes one token after complete valid headers, before cache lookup, upstream admission or body forwarding.
Validate bodies incrementally. A later malformed/oversized body or cancellation does not refund the token.
There is one bucket across HTTP and HTTPS, not one per worker, address, host, or client.
The rejected request receives 429 with `Retry-After: 1` and consumes no token.

## Selection and atomic reload

Servers may share an endpoint only if all agree on `ssl`. At most one is `default_server`.
Otherwise, the first server encountered after include expansion is the endpoint default.
Server names must be unique case-insensitively among servers sharing an endpoint.
HTTP Host matching uses only servers on the accepted endpoint. Unknown HTTP/1.1 hosts return 400 even when SNI matched.
Trim surrounding HTTP optional whitespace, then accept one ASCII DNS name with an optional decimal port from 1 through 65535.
Reject empty names, whitespace inside the value, IP literals, trailing dots, and invalid DNS labels with 400.
Remove the port and compare names case-insensitively. The port does not select another listener.
An unknown supplied Host returns 400 on either HTTP version.
HTTP/1.0 without Host uses the endpoint default. SNI certificate selection is independent, as specified in TLS.md.
Before Host is available, the endpoint default supplies header limits and timers. Request-specific settings apply after selection.

On SIGHUP the master reads and validates a complete candidate, including all includes, roots, and TLS material.
Listener endpoints, their `ssl` mode, worker count, worker_connections, upstream group names, and all toksec_* values except
toksec_rate_per_second, toksec_rate_burst and toksec_cache_ttl are immutable. Any change rejects the complete reload.
Upstream endpoints within an existing named group may change. Group-wide active/queue limits retain the same group identity
and count old and new generation reservations together. Endpoint cooldown/probe state is generation-specific.
The process-tree CPU, memory, descriptor and scratch budgets are fixed run-manifest limits, not reloadable configuration.
Root and alias targets must exist as readable directories at validation. Certificate and key files must be readable regular files.
The operator replaces fixture files before signaling and keeps the tree unchanged during candidate parsing.
The master commits one generation only after every worker can use it. Failure retains the complete previous generation and logs an error.
At commit, all cache entries are flushed and the aggregate limiter resets to a full bucket with the new settings.
Requests on old connections use this same current global bucket, while retaining old routing/TLS/request-timer settings.
Cache fills from old generations are disabled; their requests proxy normally and cannot repopulate either generation's cache.
Existing active/queued requests retain their reservations; reload does not grant them a second admission slot.
Connections accepted before commit retain their captured routing/configuration generation and close by the old generation's drain deadline. New connections use the committed generation. This differs explicitly from Stage 5 request-scoped reload.
Existing TLS connections retain their established TLS state. New accepts use the committed certificate generation.
Old generations remain alive only while needed by requests, connections, or bounded shutdown work.

Regex, rewrite, `if`, `map`, scripting, variables, DNS upstream resolution, Unix sockets, IPv6, arbitrary listen options, and disk caching are excluded.
`proxy_cache*` and `limit_req*` are excluded. Their semantics are not aliases for the extensions above.
Native directive meanings are checked against the nginx [core](https://nginx.org/en/docs/ngx_core_module.html), [HTTP core](https://nginx.org/en/docs/http/ngx_http_core_module.html), and [proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) references within the stated subset.
The release protocol must pin an nginx oracle version and build before this draft becomes an accepted task.


# Stage 10 HTTPS contract

Status: proposed builder reference. Runtime dependency packaging and independent verification remain publication gates.
All HTTP.md requirements apply to decrypted HTTP/1.1 traffic. HTTPS uses the same routing, cache, limiter, and worker budget as plaintext.

## Approved dependency

The sandbox supplies one pinned OpenSSL build, including libssl, libcrypto, headers, API documentation, and runtime dependencies.
C++ links that build directly. Rust calls the same C ABI through source-defined FFI declarations.
The publication manifest must record the exact version, build options, hashes, and compiler/linker recipes for both languages.
Those values are not frozen in this draft. A host's incidental OpenSSL installation does not satisfy this requirement.
Downloaded crates, other crypto libraries, HTTP frameworks, subprocess TLS proxies, and handwritten cryptography are excluded.
OpenSSL memory, CPU, and descriptors count toward the aggregate process-tree limits in INTERFACE.md.

## Directives and fixtures

| Directive and complete argument form | Context | Default and inheritance |
|---|---|---|
| `ssl_certificate PATH` | http, server | No default. Inherits from http if absent in server. One PEM chain file. |
| `ssl_certificate_key PATH` | http, server | No default. Inherits from http if absent in server. One unencrypted PEM private key. |
| `ssl_protocols TLSv1.2 TLSv1.3` | http, server | Both versions. This is the only accepted argument sequence. Inherits if absent. |

Each occurs at most once in its context. Paths follow CONFIGURATION.md and contain no variables.
Every server on an `ssl` endpoint requires an effective certificate and key pair.
Validation rejects unreadable or malformed PEM, an empty chain, a mismatched key, and keys other than RSA-2048.
The leaf is first in the chain. Any intermediates follow in issuer order. The trust root need not be sent.
The fixture packet supplies a test CA and two independently verifiable chains with DNS SANs `alpha.test` and `beta.test`, respectively.
Each certificate has exactly its corresponding DNS SAN. Common Name fallback is not an acceptance condition.
Fixtures also supply replacement RSA-2048 chains with the same names and different serial numbers for reload checks.
Fixture certificates are valid throughout the declared test clock interval. Fixture private keys are test-only inputs.
Clients verify the fixture CA, validity interval, chain, and expected hostname. Disabling verification cannot demonstrate success.
The sample listener is `127.0.0.1:8443`; plaintext uses `127.0.0.1:8080`.

## Protocol policy

TLS 1.2 and TLS 1.3 are both required. Older versions fail the handshake.
TLS 1.2 permits only `ECDHE-RSA-AES128-GCM-SHA256` and `ECDHE-RSA-AES256-GCM-SHA384`.
TLS 1.3 permits only `TLS_AES_128_GCM_SHA256` and `TLS_AES_256_GCM_SHA384`.
Supported key-exchange groups are X25519 and secp256r1. Either common permitted cipher and group may be selected.
The OpenSSL provider's supported RSA-PSS and RSA-PKCS1 SHA-256 or SHA-384 signature schemes may be used where the negotiated TLS version permits them.
No session IDs, session tickets, or PSK session resumption are accepted. TLS 1.3 ticket issuance and early data are disabled.
Clients receive a full handshake on every new connection. TLS renegotiation and client authentication are disabled.
The only selectable ALPN protocol is `http/1.1`. A client offering it negotiates it even when the same list also contains `h2`.
A client without ALPN may exchange HTTP/1.1. A nonempty ALPN list without `http/1.1` fails with `no_application_protocol`.
There is no HTTP/2 fallback or advertisement.

## SNI and HTTP routing

An ASCII DNS SNI name matches server_name case-insensitively among servers on the accepted listener.
Absent or unknown SNI uses the endpoint default server's certificate. Malformed TLS or malformed SNI encoding fails the handshake.
The SNI name does not rewrite or constrain the later Host field.
For example, SNI `alpha.test` plus Host `beta.test` presents alpha's certificate and serves beta's HTTP route.
The client must verify alpha's identity in that example. HTTP/1.1 Host validation still rejects missing, duplicate, or unknown Host.
Certificate selection does not leak across connections, workers, or reload generations.
The same protocol policy applies to every server on a listener, including the default.

## Nonblocking I/O and reload

Fragmented ClientHello records, partial TLS reads and writes, and OpenSSL WANT_READ or WANT_WRITE states must make progress without blocking other clients.
Readiness registration follows the operation OpenSSL requests, even when a write requires reading or a read requires writing.
There is no busy polling while a peer is stalled. Handshakes count against downstream admission and per-worker connection limits.
The absolute handshake timer starts at accept. Expiry closes the connection without an HTTP response.
HTTP deadlines begin at their specified HTTP events after handshake completion. The HTTP response framing must match the decrypted bytes.
A peer close_notify terminates TLS input. A transport EOF without close_notify is an unclean close.
Incomplete HTTP input is never accepted as a complete request or body because the TLS transport closed.
After either input close, complete accepted work may finish only if writes remain possible and its existing deadlines permit it.
An unclean close does not invalidate an already complete, correctly framed response seen by the client.
On local close, attempt close_notify without blocking. Do not wait more than 1 second or beyond the remaining drain deadline.
Close transport and release all connection state when the bound expires.

SIGHUP loads fresh certificate bytes even when certificate paths are unchanged.
The master validates the whole candidate before commit. Invalid keys or certificates retain the previous complete generation.
New accepts after commit use the new certificate. Already accepted connections retain their captured TLS generation, including incomplete handshakes.
Existing TLS connections retain both their TLS and routing generations, bounded by the old generation's drain deadline.
Certificate contexts remain alive until their connections finish. Worker replacement uses the currently committed generation.

Encrypted upstreams, mutual TLS, ACME, OCSP, custom cipher directives, HTTP/2, and HTTP/3 are outside this profile.
The native TLS directive subset is based on the nginx [HTTPS module reference](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).
The fixed algorithms, ALPN behavior, resumption policy, and closure bounds above are explicit Toksec profile choices.


# Cache, worker and recovery behavior

This file defines Stage 10 additions to HTTP.md. Configuration directive names
and values are in CONFIGURATION.md. All deadlines use monotonic time.

## Cache and coalescing

Cache successful proxy GET responses with explicit Cache-Control:
public,max-age=N, capped by the configured cache TTL. The key includes downstream
scheme, normalized HTTP host, target path and query. Honor Vary: Accept-Encoding
using its exact request field value, with absence distinct from a present value.
Bypass Vary:*, other Vary names, Authorization requests and Set-Cookie, private or
no-store responses. Do not cache partial responses, malformed/truncated bodies,
or 5xx errors. HEAD may read a completed GET entry but never populate one.

An expired entry with an ETag uses If-None-Match upstream. If it lacks ETag but
has Last-Modified, use If-Modified-Since. A valid 304 refreshes the stored body
using returned freshness/validator headers, retaining absent stored fields;
return a normal body-bearing 200 to an unconditional GET. A fresh 200 replaces
the entry only after its complete body validates. Without a validator fetch a
new representation. Never serve an expired entry on refresh failure in this
profile. Complete waiters with the applicable 502/504 and permit later recovery.

Store cache entries and coalesce misses within each worker. A single-worker cold
burst for one cacheable key produces one in-flight upstream fetch. With W workers
at most W simultaneous fetches are allowed for that key. Partition the configured
total cache body-byte allowance equally across workers; unused shares need not
be borrowed. Metadata and waiting requests must also be bounded by explicit entry
and waiter limits. The memory budget applies to the entire process tree.

Do not coalesce POST, HEAD misses, Authorization requests or different variants.
Before Vary is known, include Accept-Encoding in the pending key. When a response
proves noncacheable or too large for a worker's cache allowance, release waiters
into ordinary FIFO proxy admission; do not silently reuse that response for them.
Queue deadlines continue from each waiter's original arrival. The initiating
client's disconnect must not cancel a fetch with remaining live waiters. With no
clients left, abort the upstream exchange and do not retain a partial entry.

## Global limits and upstream failure policy

Rate limiting and configured connection/admission limits apply across all workers,
not independently per worker. The global HTTP request limiter is a monotonic token
bucket with the configured rate/burst. Rejections are 429 with Retry-After: 1.
Benchmarks disable the request limiter except designated correctness/fairness cases.
Separate configured upstream groups have separate FIFO admission queues and limits.
Retries share their request's admission budget; they do not create unlimited work.

After an endpoint's configured consecutive transport/deadline failure threshold,
exclude it from new selection for the configured cooldown. Existing exchanges may
finish. After cooldown permit a single probe exchange at a time; success restores
eligibility, failure restarts cooldown. With no eligible endpoint or available
probe, return 503 with Retry-After: 1. Valid upstream HTTP error responses do not
by themselves count as transport failure. Keep protocol-invalid connections out
of the reusable pool. The directive table specifies the threshold/cooldown values.

## Master and workers

Run exactly the configured 1, 2 or 4 workers beneath one foreground master. Use
the same executable; no external helpers. Each worker must be able to serve all
configured listener types. Threads and the I/O mechanism remain implementation
choices. Global limits may use any permitted IPC strategy.

If the host kills one worker, the master replaces it within two seconds after
observing exit. Requests owned by that worker may fail. Other workers must remain
serviceable, and the process tree must not accumulate zombies or leaked IPC.
Tests identify workers through the process tree, not a candidate-supplied PID list.
Cache contents owned by an exited worker may be lost. Global admission/rate-limit
state must recover that worker's reservations without permanently reducing capacity.

SIGHUP validates an entire new configuration plus TLS material before publication.
CONFIGURATION.md enumerates immutable directives and fixed run-manifest resource
budgets; changes to those directives reject the reload. Other documented reloadable settings switch
as one generation. New connections use the new generation within two seconds.
Existing connections and in-flight operations may finish on their accepted
generation. Their keepalive lifetime ends at the configured drain deadline.
This is an explicit Stage 10 change from Stage 5's subsequent-request reload scope.

Flush cache for the new generation; old in-flight responses cannot repopulate it.
Reset the single global limiter on a successful generation change; old and new
connections both consume the newly configured bucket. Preserve upstream group
reservations across generations, keyed by the immutable group name. Cache/admission state retained
by old connections still counts against process-tree resource limits. An invalid
reload leaves the active generation, certificate and listeners serving unchanged.
The old and new configurations are immutable snapshots from request processing's
perspective; internal representation remains the agent's choice.

SIGTERM stops new accepts within 250 ms, finishes in-flight responses up to the
configured drain deadline, and exits the complete process tree within that deadline
plus 500 ms. Idle connections close; an incomplete request cannot extend draining.
Never start replacement workers while shutting down.

## Sustained operation

Independent correctness tests combine disconnects, queue pressure, cache expiry,
failed reload, certificate rotation and worker exits. Required behavior is the
same as above even when events overlap. A worker kill may interrupt its owned
requests; it does not waive correctness for responses that are completed.

After clients close and configured idle/pool deadlines pass, live socket and queue
reservations must return to their pre-wave baseline, apart from explicitly bounded
idle pools/cache entries. Repeat waves must not grow descriptors, processes or
charged memory without bound. Host tests disclose allowed accounting tolerance
and observation deadlines before this packet is frozen for launch.


# Declared benchmark design

Status: uncalibrated design, not an executable benchmark contract yet. Final
numeric durations, class rates and validity thresholds must be frozen in the
published workload manifest before an agent run. The agent receives that manifest;
only workload implementation and sampled fault schedules remain host-only.

Final performance requires the complete API gate. Development benchmarks are
provisional and may run against a smoke-accepted candidate. Do not interpret a
successful visible HTTPS GET as full correctness or performance acceptance.

| Family | Transport | Body | Concurrency | What is measured |
|---|---|---|---|---|
| Static fresh | HTTP, TLS 1.2, TLS 1.3 | 4/64 KiB | 256/4096 | Full connection/request latency and useful responses/s |
| Static persistent | HTTP, TLS 1.2, TLS 1.3 | 4/64 KiB | 256/4096 | Steady response latency and goodput |
| Proxy persistent | HTTP, TLS 1.2, TLS 1.3 downstream; HTTP upstream | 4/64 KiB | 256/4096 | Correct proxied goodput, queue pressure, upstream attempts |
| Cache hit/miss/refresh | HTTP and HTTPS | 4/64 KiB | 256/4096 | Response latency and origin request reduction |
| Streaming | HTTP and HTTPS | 16 MiB transfers with small-request side traffic | Calibrated bounded transfer concurrency | Time to first byte, bytes/s, memory and small-request tail latency |
| Mixed recovery | HTTP and HTTPS | Declared mix | 256/4096 total | Per-class goodput, tail latency and recovery after disruption |

Run server process-tree profiles of 1, 2 and 4 CPUs, always with the same 512 MiB
aggregate memory budget. Use five repetitions for scored workloads. Fix and record
TLS protocol/cipher/key parameters. TLS session resumption and early data are off.
Report fresh full-handshake and persistent measurements separately. Clients verify
certificate chains/hostnames and exact decrypted payloads. No resumption or TLS
verification bypass is permitted merely to improve the measured number.

Report successful requests/s, useful bytes/s, p50/p95/p99, errors by status/type,
connect/handshake/response timeout phases, rejection rate, CPU and charged memory
for the entire candidate process tree. Retain upstream request counts, worker
replacement events, per-class results, per-round spread and eligibility reasons.
Account for exited/replaced workers as well as live processes.

Generator and fixture CPUs are outside the server allocation. Calibrate TLS
handshake capacity and upstream capacity separately. Track scheduling wait or
equivalent stall evidence for server and upstream, not only generator lag.
Insufficient load-generation capacity makes a round inconclusive. Do not promote
an ineligible measurement or hide failed/rejected requests in successful latency.

The published mixed-workload schedule must specify class proportions, request
sizes, offered-rate or closed-loop semantics, warmup/measurement/drain periods,
fault windows, allowed interrupted requests and recovery deadlines. No hidden
requirements may be introduced through the schedule. Until that manifest and
calibration exist, no Stage 10 performance grade can be issued.


# Minimal visible smoke checks

The host supplies these descriptions and ordinary example inputs. It does not
ship the checker implementation or its edge-case fixtures to the builder.

1. bootstrap: one ordinary plaintext GET of /hello.txt returns 200, exact bytes,
   Content-Length and a closing response to Connection: close. This uses the separate minimal bootstrap.conf and is the first-tag eligibility gate.
2. config: --check-config accepts the ordinary supplied nginx.conf and exits zero.
3. https-get: one ordinary HTTPS GET returns the same file, with trusted fixture
   CA and hostname verification enabled by the client.
4. https-persistent: two sequential ordinary GETs on one HTTPS connection succeed.
5. proxy: one ordinary proxied GET returns the fixture upstream's exact body.

A tag may be published once bootstrap passes. Every new tag must compile, pass
bootstrap and preserve previously passing visible checks. Missing later checks
are recorded as incomplete rather than preventing every early release. Smoke
success does not establish final API correctness or final performance eligibility.

There are deliberately no visible tests for malformed syntax, large headers,
missing fields, TLS negotiation edge cases, worker crashes or overload. Design
your own tests from the complete public contract. Their absence from the smoke
suite does not remove them from the assignment.


Operational campaign notice, authoritative over draft availability statements:
The shared RULES.md above is the current policy. This stage has sandboxed
compilation, standalone tests and ordinary smoke feedback. Independent API
coverage is partial, and performance measurements are provisional diagnostics.
Neither passing the available API checks nor a diagnostic establishes full-stage
acceptance or final performance credit. The full acceptance suite and calibrated
performance matrix remain incomplete.

Implement the server, configuration, HTTP parsing, workers and TLS integration
yourself. OpenSSL headers/libraries are supplied, not server code. The controller
reports a strict $4 model-spend cap for this run; any enclosing
campaign ledger also limits admission. Standard service tier and medium reasoning
are used. Requests are counted before admission. Reasoning and text share the
enforced output limit, so prefer complete bounded improvements.

Your full latest source and notes are retained outside request context. read_source
retrieves omitted source. run_tests compiles a standalone test executable; it
starts no candidate automatically. read_input accepts artifact.json, packet-relative
builder/ or fixtures/ paths, and approved OpenSSL headers under openssl/.
Certificate private keys are public test fixtures. Read capacity for effective
sandbox task and descriptor limits. Per-process limits enforce the total descriptor
bound across the bounded process tree.


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
  "stage": 10,
  "submission": {
    "encoding": "utf-8",
    "max_bytes": 1048576,
    "source_file": "main.cpp"
  }
}

```

