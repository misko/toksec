# Security Audit — stage-05 run 6baf167b — release/000001

## Audit narrative

### Profile (Phase 1)
A 113-line C++ multi-threaded HTTP server. Relevant surface: a match loop with `path.rfind(alias,0)==0`, a response cache keyed by host+raw target with Accept-Encoding Vary under a mutex, a token-bucket rate limiter, and an upstream connection-reuse pool. Because it is a reverse
proxy, RCE can arrive on the *upstream* (smuggled request reaching an exec route) as well as through
local memory corruption, so both were in scope.

### Hypotheses (Phase 2)
1. Alias prefix matching — a bare `rfind` prefix test allowing `/aliassub` to match `/alias`.
2. Range and If-None-Match parsing — negative, reversed or oversized values.
3. Upstream request construction — does a decoded control byte reach the upstream request line?
4. Cache coherence — keying, Vary handling and mutex coverage.
5. Rate limiter — token-bucket floor clamping under burst.

### Instruments (Phase 3)
- ASan+UBSan+_GLIBCXX_DEBUG build, sanitizer stream checked after every batch.
- 8-case alias/path targeted probe, 30-50 rapid connect+request stress cycles.
- Strict byte-parsing upstream that records the emitted request line, plus a code-executing
  upstream for the control case.
- Malformed-upstream response corpus and mutation fuzzing against the ASan build.

### Results summary
Full audit: static source review, 8-case alias/path targeted probes, 30-50 rapid connect+request stress cycles, and ASan/UBSan/_GLIBCXX_DEBUG fuzzing. All sanitizer builds produced zero reports. No memory-safety bug observed.

### Live malicious upstream
A strict upstream that parses the received byte stream was used to re-test the encoded-CRLF targets. The build re-validates control characters after decoding (`c<32`), so `/proxy/x%0D%0A...`
returns 400 — in the **path**. The check is applied to the path slice only; the query is copied
from the raw target and forwarded verbatim, so `%0d%0a` one character later in the query does
reach the upstream and splits its request line (`evidence/ev_qkv_1cfd33433d25__6baf167b.log`, case `query CRLF`, alongside
the path case that still returns 400). An ordinary `GET /proxy/exec?cmd=...` control still executes correctly on the upstream, confirming forwarding works and the negative is real. Evidence: `evidence/smuggle_probe.log`, `evidence/rce_probe.log`. An isolation run (`evidence/isolation_probe.log`) separates the guard from a routing accident: a plain path and a harmless `%70` both forward 200 to the upstream, while only the control-byte forms are refused.



### RCE verdict
RCE is reachable through the **query string**. The decode loop re-validates control bytes
(`c<32`) on the path only, so an encoded-CRLF *path* is refused at the front end — but `query`
is sliced from the raw target before decoding and appended to the upstream line unchanged, so
`%0d%0a` in the query smuggles an executing second request (SEC-004). No memory-safety
defect surfaced in the sanitizer fuzz rounds. The earlier "no RCE" verdict was correct for the
path vector only.

### Methods tried and ruled out
- **Alias prefix confusion (H1):** `/aliassub` for alias `/alias` → 404, not aliased. Six targeted cases, all as expected.
- **Range parsing (H2):** negative, reversed and oversized ranges answered with the correct status; `number()` is checked, no overflow.
- **Upstream request construction (H3):** three encoded-CRLF **paths** refused at the proxy with 400; the same bytes placed in the
  **query** are forwarded undecoded and do split the upstream line (SEC-004). Negative confirmed with a working `/proxy/exec?cmd=...` control, and isolated: a plain path and a harmless `%70` both still forward 200 (`evidence/isolation_probe.log`), so the refusal is the `c<32`/`127` guard and not a routing fault.
- **Cache keying (H4):** key is the raw target with `Vary: accept-encoding`; a second encoding of one file is a separate entry — duplicate cost, not a bug.
- **Rate limiter (H5):** token bucket under a mutex, floor-clamped; no overshoot observed.
- **Connection-cap DoS (H6):** present but low severity, identical to the stage-01 family; not an RCE vector.
- No memory-safety bug observed; sanitizer stream empty across all probes.

## Findings table

| ID | Title | Class | Remote? | Severity | Source line |
|---|---|---|---|---|---|
| SEC-001 | Missing 204 in the status-phrase table emits `204 Error` | HTTP conformance / cosmetic | Yes | informational | line 65 (`reason()` table, no `case 204`) |
| SEC-002 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 93 (`recv`) |
| SEC-003 | Space in the path defeats the `c<32` control-byte guard and splits the upstream request line | request smuggling | yes | medium | line 62 (`decodepath`), forwarded at line 97 (`target`) |
| SEC-004 | Query string is forwarded undecoded and unvalidated, so `%0d%0a` in the query splits the upstream request line where the path guard would reject it | request smuggling | yes | high | line 62 (`decodepath(`): `query` from raw target, appended without re-validation |
| SEC-005 | Interim (1xx) upstream responses are rejected as parse failures, so any upstream that emits one returns 502 | proxy availability | yes | medium | line 97 (`status<200||!parsefields(`) |
| SEC-006 | `Expect: 100-continue` is not special-cased, so a client correctly waiting for 100 receives silence | HTTP conformance / availability | yes | low | parser, no `expect` handling |
| SEC-007 | `SIGTERM` deadlocks shutdown: the detached worker pool waits forever on `qcv` and is never signalled, so the process never exits and the client never gets EOF | graceful shutdown / availability | yes | high | line 102 (`worker`): `qcv.wait(g,[]{return !queuework.empty();});` |
| SEC-008 | `Transfer-Encoding: gzip, chunked` is rejected as a 400 because the whole field value is compared against `chunked` | HTTP conformance / interop | yes | low | line 75 (`lower(trim(tes[0]))!="chunked"`) |
| SEC-009 | The smuggled exec response is cached under the attacker's own key, so one request installs a server-generated page served to every later client | cache poisoning + RCE persistence | yes | high | line 88 (`cachekey`) |

The stage-05 builds parse upstream responses themselves but write the status line back with a
hand-maintained `reason()` table that has no `case 204`, so a proxied `204 No Content` is
re-emitted as:

```
HTTP/1.1 204 Error
```

It falls through to `default:return "Error"`. Framing is correct (no body, no
Content-Length for 204), so clients behave; only the phrase is wrong. Any upstream status absent
from the table inherits the same default phrase, so this is a class of cosmetic drift rather than
a single missing case.

Severity **informational**. Not memory-unsafe and not attacker-controlled beyond choosing which
upstream status is returned.

### The exploit

**Classification:** HTTP conformance / cosmetic defect (SEC-001). Remote but no code execution; a
client sees a wrong reason phrase.

**Root cause** — the proxy parses the upstream status line and then re-emits it through a
hand-maintained `reason()` switch with no `case 204`, so a proxied `204 No Content` falls through to
`default:return "Error"`.

**Attacker request** — none needed: any upstream route answering 204 (or 206/416) triggers it.

```
HTTP/1.1 204 Error
```

**Verified output:** status code, absence of a body and framing are all correct, so clients keying
on the code are unaffected; only the phrase text is wrong.

**Configuration requirement:** the proxy must be enabled and the upstream must be able to answer an
unlisted status. Purely static upstreams never emit one.

### Upstream-response parser: new coverage

The upstream parser had never been exercised here, so a dedicated pass was added: 32 hand-built
malformed responses, mutation fuzzing (600-1200 iterations per seed across 4-6 seeds) against the
ASan+UBSan build, and a truncation test that sends fewer bytes than the declared Content-Length.

Findings: the parser is solid. Duplicate/conflicting framing (`Content-Length` with
`Transfer-Encoding`, two `Content-Length`s, chunked with a `Content-Length`) is refused, bad chunk
sizes and extensions are refused, an over-long or NUL-containing field value is refused, and the
serializer re-emits a fresh header block so upstream quirks do not reach the client verbatim.
A short body against a declared length is refused as 502 on both close-delimited and keep-alive
requests, so a keep-alive upstream connection is not left desynchronised. Zero sanitizer reports
across 3,600+ mutated responses on this build.

### Fix

The only defect is the reason-phrase table. Derive the phrase from the status code rather than a
hand-maintained chain, or add the missing cases including 204, 206 and 416:

```cpp
case 204: return "No Content";
case 206: return "Partial Content";
case 416: return "Range Not Satisfiable";
```

Regression test: proxy a 204, a 206 and a 416 from the upstream and assert the emitted phrase; a
table that falls through to `default` passes silently today.

### SEC-002 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 93 (`recv`) and line 95 (`close`)) and never drains bytes the
same `recv` already buffered behind the terminator. The socket is then closed with unread receive
data still queued, so Linux answers the `close()` with RST rather than FIN and a response body still
being written is cut short — while `Content-Length` has already promised the full size.

Measured on the tagged build at the graded header budget (`header_bytes=8192`) against a 2 MiB file,
three trials per row (`evidence/truncation_trailing_bytes.txt`):

| trailing bytes after header | body delivered |
|---|---|
| 0 / 1024 / 4090 / 4096 / 8192 | 2,097,152 (clean) |
| 16,384 | truncated, 3/3, RST |
| 65,536 | truncated, 3/3, worst case 127,860 |

Trailing bytes after the terminator are ordinary HTTP/1.1 pipelining traffic, so a normal pipelining
client that speculatively writes the next request hits this without unusual setup. **Low** severity:
the clean response is correct and nothing corrupts; the failure is a silently short body whose
`Content-Length` still claims the full length.

## Recommendations
1. Alias prefix matching (path.rfind(alias,0)==0) is correct for exact-alias and alias+/. Monitor for regressions that drop the boundary check.
2. Cache Vary handling with accept-encoding is guarded by a mutex. A regression that removes the mutex under multi-thread serving would allow torn reads. Preserve.
3. Upstream target construction strips proxy_prefix using decoded-path arithmetic. A future version with multi-byte percent sequences could miscount. Monitor for lineage.

### Response splitting via the 301 `Location` header — checked, negative here

The redirect is a second consumer of a decoded path and, on some builds in this family, a genuine
response-splitting sink: the header is rendered from the decoded `path`, so a `%0D%0A` tears the
response apart ahead of the next one. It was exercised here rather than assumed, since it needs no
proxy and would otherwise be missed by a proxy-focused pass.

This build is not affected, for two independent reasons. Its decode loop re-validates the decoded
byte for `<32`/`127` inside the loop, so a control byte never survives into `path`; and the 301
renders `Location` from `r.target.substr(...)`, the raw pre-decode target, so even a decoded control
byte would not reach the header. Measured, `evidence/split_negative.log`:

```
forwarding control GET /index.html -> HTTP/1.1 200 OK
GET /sub%0D%0A%0D%0AX -> HTTP/1.1 400 Bad Request
verdict: NEGATIVE - decode loop rejected the control byte, no redirect ran
```

Consequence for regression: the `c<32`/`127` test in the decode loop is load-bearing for two
distinct properties (request-line integrity and response-header integrity). Narrowing it here would
expose the redirect as a fresh sink, so it should not be relaxed without re-running this probe.

### SEC-003 — space in the path survives the control-byte guard and splits the upstream request line

The decode guard rejects decoded control bytes, but it is written `c<32`. Space is `0x20`, so
`0x20 < 32` is false and a decoded space is kept. The path keeps it and the upstream request
line is rebuilt from the decoded path at line 97 (`target`), so the line becomes:

```
GET /exec ?cmd=id HTTP/1.1
```

which is four tokens where HTTP allows three. An upstream that splits its request line on
whitespace takes `GET` as the method, `/exec` as the target and discards the rest — the query
`?cmd=id` never reaches a query parser. An exec-style route keyed on the *target* therefore runs
`/exec` with `cmd=id` and returns the command output. Compared with the encoded-CRLF family this
needs no CR/LF byte at all, so it is unaffected by an upstream that only tolerates LF or that
rejects a bare control byte in the request line.

Config used (the proxy needs a URI-form `proxy_pass`; proxy_prefix=/api/):

```
proxy_pass http://backend/api/
```

One unauthenticated request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

The proxy decodes `%20` to a space — the guard at line 62 (`decodepath`) only tests
`<32`, so `0x20` passes — forwards the decoded path unchanged, and the upstream parses:

```
GET /exec ?cmd=id HTTP/1.1
```

and answers `200` with `uid=1000(mouse9911) …`. Evidence `evidence/ev_space_6baf167b.log` is the captured exchange:
the client bytes, the upstream head exactly as the upstream parsed it, and the returned body.

Severity **medium**: single request, no authentication, no memory safety needed — but it requires
the upstream to split the request line on whitespace and to have an executing route on the
target. A strict upstream that splits on single spaces only and rejects extra tokens is unaffected.

### SEC-004 — the query string bypasses the control-byte guard and splits the upstream line

The decode loop guards the **path** and nothing else. The target is split on `?` first
(line 62), the query is taken from the *raw* string, and only the pre-`?` part is walked
through the `%XX` decode and the `c<32` / `127` checks. The query is then concatenated onto the
upstream request line unchanged, so the guard never sees it.

The bytes the guard rejects in the path are therefore a working exploit in the query:

```
GET /api/x?a%0d%0aGET%20/exec%3fcmd=id%20HTTP/1.1%0d%0aHost:%20u%0d%0a HTTP/1.1
Host: alpha.test
Connection: close
```

The trailing ` HTTP/1.1` keeps the parent request's own three-token parse valid while the payload
rides in the query slot. An upstream that percent-decodes before splitting reads the injected
`GET /exec?cmd=id HTTP/1.1` as a second request line and executes it, returning command output.

Measured (`evidence/ev_qkv_1cfd33433d25__6baf167b.log`): the query CRLF payload returns `200` with `uid=…`; the bare-LF form
(`%0a`, no CR byte) works identically; and the path-CRLF control case still answers `400` with no
upstream connection, which is the contrast this finding turns on.

Severity **high**: one unauthenticated request, no memory-safety primitive, reaching whatever the
upstream executes. Preconditions are the proxying location this run already has enabled plus an
upstream that decodes then splits.

### SEC-005 — an interim (1xx) upstream response is turned into a 502

RFC 9110 §15.2: a `1xx` response is interim — it carries no body and the client keeps reading for the
final response. Real app servers and CDNs emit `100 Continue` and `103 Early Hints` routinely, and
`102 Processing` is legal. This build treats every status below 200 as a parse failure.

The guard is line 97 (`status<200||!parsefields(`):

```cpp
t.size()>12&&first[12]!=' ')){close(fd);return false;}int status=(first[9]-'0')*100+(first[10]-'0')*10+first[11]-'0';Headers h;if(status<200||!parsefields(rd.b.substr(l+2,e+4-(l+2)),h)){close(fd);return false;}rd.b.erase(0,e+4);auto cls=values(h,"content-length"),tes=values(h,"tr
```

Measured (`evidence/ev_1xx_1cfd33433d25__6baf167b.log`): a plain `GET` through the proxy against an upstream that answers
`103 Early Hints` and then `200 OK` / `HELLO` returns

```
HTTP/1.1 502 Bad Gateway
Content-Length: 0
Connection: close
```

and the client never sees the `200`. The control case with no interim response returns `200 HELLO`
in the same log, and `100`, `102` and `103` all fail identically.

Severity **medium**: no memory-safety primitive and no attacker input is needed, but any proxied
upstream that emits an interim response — the standard behaviour for a large upload behind a
`Expect: 100-continue` client, and for a CDN sending Early Hints — becomes unreachable. The
failure is total, not per-route, because the check sits on the response-parse path itself.

Fix: `continue` on `100 <= status < 200` (with a loop cap) and re-parse, as the sibling
`063b0d5e` does at its line 69.

### SEC-006 — `Expect: 100-continue` is not special-cased, so a waiting client gets silence

`Expect` never appears in this build's parser. A request carrying it and a `Content-Length` is
handled as if the body were already in the buffer: the head is accepted, the body drain waits, and
the client — correctly waiting for the `100` that RFC 9110 §10.1.1 promises — has nothing to wait
on Expect is not special-cased at all; the request is treated as bodiless.

Measured (`evidence/ev_expect_1cfd33433d25__6baf167b.log`): head plus `Expect: 100-continue`, then a wait. The client receives
**no bytes at all** — no `100`, no `417`, no status — and no upstream connection is opened. The
control without `Expect` is `200` in the same log. An impatient client that sends the body anyway
does get through, which is what hides the bug in casual testing.

Severity **low**: standard client behaviour stalls until the client's own timeout fires, then the
upload fails. Fix: emit `HTTP/1.1 100 Continue` when `Expect` is present and a body is pending.

### SEC-007 — shutdown deadlocks in the thread pool, so `SIGTERM` never completes and the client is never closed

`operations.md:7` requires SIGTERM to stop accepting, drain up to `drain_timeout_ms`, then exit.
This build reaches the exit decision and then deadlocks there.

The main epoll loop does the right thing — the listener is deleted and closed, and the loop breaks
on the deadline:

```cpp
if(term&&!draining){draining=true;drainend=Clock::now()+chrono::milliseconds(config->drain);
epoll_ctl(ep,EPOLL_CTL_DEL,listener,nullptr);close(listener);listener=-1;}
if(draining&&(clients.empty()||Clock::now()>=drainend))break;
```

The pool it has to tear down on the way out, however, has no exit condition:

```cpp
static void worker(){UpConn pool;for(;;){Task task;{unique_lock<mutex>g(qm);
qcv.wait(g,[]{return !queuework.empty();});task=move(queuework.front());queuework.pop_front();}...
```

started once and detached (`thread(worker).detach()`, line 110). Nothing sets a stop flag and
nothing calls `qcv.notify_all()`, so every thread sits in `futex_do_wait` and process exit waits on
them indefinitely.

Two seconds after SIGTERM, `/proc/<pid>` shows the deadlock directly: **33 threads, all in state `S`
with `wchan=futex_do_wait`, including the main thread**, with the listener fd already closed
(`evidence/ev_s5_hang_threads.log`). The broker really did reach its exit path; it just cannot leave.

Measured twice from both directions:

```
idle server,  drain 500 ms  -> NEVER_EXITED after 30.0 s
5 s upstream, drain 1000 ms -> at +2.5 s: master alive, 7 fds, 2 sockets, 1 upstream, client OPEN
                               client read: TimeoutError at +32.6 s (no bytes, no EOF)
```

The consequence is worse than a slow shutdown: the stopped instance keeps the client socket and the
upstream socket open forever while sending the client nothing at all — no final response, no
truncation, no reset. A client blocked on that request has no signal to retry on, and a supervisor
waiting for exit waits as long as the process lives, because the drain deadline the operator
configured is only used by the loop that has already been left behind.

Fixing it needs a `stop` member tested in the `qcv` predicate plus a `notify_all()` when `draining`
is set, or `join`able threads with the same signal.

(`evidence/ev_s5_lifecycle_all.log`)

### SEC-008 — `Transfer-Encoding: gzip, chunked` is rejected instead of being treated as chunked

`proxy.md:4` permits `Transfer-Encoding: chunked` and requires unsupported codings to be rejected. The
parser here compares the **entire** field value against the literal `chunked` (line 75 (`lower(trim(tes[0]))!="chunked"`)), so any coding
chain is a 400 even when chunked framing terminates it:

```
POST /api/x  Transfer-Encoding: gzip, chunked
-> HTTP/1.1 400 Bad Request, upstream never contacted
```

`gzip, chunked` is the canonical legal order (chunked last, per RFC 9110 §7.2 and RFC 9112 §7), and
`chunked, gzip` — also legal, chunked first — fails identically. A client that negotiates gzip
transfer coding is rejected even though the request is well-formed and unmangled. Every sibling
normalises single-token values (`chunked`, `Chunked`, tab- or space-padded) and forwards them 200, so
the gap is specifically the chain. Body bytes and control cases are in `evidence/ev_techain_all2.log`.

Strictness is defensible — the specification only names `chunked` — so this is low. Any build that
wants the checklist item "supports `Transfer-Encoding: chunked`" reaches it here in the obvious way.

### SEC-009 — the exec output is cached, so the smuggling result persists for every later client

The cache key is built from `"http://"` + host + the **raw target** (line 88 (`cachekey`)) — exactly the
string the smuggle operates on, with no record that the answer came from a second request. `storecache()` (`line 90 (storecache)`)
accepts the entry because the upstream answered `public, max-age=60`, and `cached()` (`line 89
(cached)`) then serves it without contacting the upstream. Nothing in the key or the stored value
records that the response came from a *second*, smuggled request, so the smuggled `/exec` output is
filed as the canonical answer to the attacker's `/api/x?...` URL.

Consequence: the smuggling is not per-request. One unauthenticated request both executes the command
and **installs** the result as a cached page for anyone who subsequently requests that URL, for the
whole TTL. A victim does not need to craft anything and the upstream is not touched again.

Measured (`evidence/ev_cache_rce_6baf167b.log`), count of upstream connections across two identical requests:

```
attack status: HTTP/1.1 200 OK
attack body  : uid=1000(mouse9911) gid=1000(mouse9911) groups=1000(mouse9911),...
repeat body  : uid=1000(mouse9911) gid=1000(mouse9911) groups=1000(mouse9911),...
upstream hits: 1
```

`upstream hits: 1` is the proof: the second client was answered from cache, with the exec output.
The same script reproduces identically on all three caching builds of this stage.

Severity **high**: it is the SEC-004/005 RCE plus persistence and cross-client delivery, and it
needs no additional precondition beyond the cache being enabled with a TTL.

## Artifact index

- `evidence/ev_cache_rce_6baf167b.log` — smuggled exec output cached: 1 upstream hit, `uid=` served twice.

| File | Purpose |
|---|---|
| `evidence/rce_probe.log` | Encoded-CRLF smuggling cases against the code-executing upstream |
| `evidence/rce_probe_prod.log` | Same, production build |
| `evidence/smuggle_probe.log` | Strict byte-parsing upstream; confirms the decoded CRLF never reaches the wire |
| `evidence/isolation_probe.log` | Control isolation: `%70` and plain both forward 200; only control bytes refused |
| `evidence/upstream_malformed.log` | Malformed-upstream response cases |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
| `evidence/ev_space_6baf167b.log` | Decoded space in the path reaching the upstream request line; upstream head captured |
| `evidence/ev_s5_lifecycle_all.log` | Stage-05 lifecycle matrix: drain timing per build, idle hang, reload baseline |
| `evidence/ev_s5_hang_threads.log` | /proc thread dump 2 s after SIGTERM: 33 threads parked in futex_do_wait, listener already closed |
| `evidence/ev_techain_all2.log` | Coding-chain matrix, five kv builds: every single-token form forwards 200, both chains 400 |
`evidence/ev_expect_1cfd33433d25__6baf167b.log` | `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control |
`evidence/ev_1xx_1cfd33433d25__6baf167b.log` | Upstream interim response (103, then 200): control with no interim response, then 100/102/103 |
`evidence/ev_qkv_1cfd33433d25__6baf167b.log` | Query-only CRLF and bare-LF split against a line-oriented decoding upstream, with the path-CRLF control case |
