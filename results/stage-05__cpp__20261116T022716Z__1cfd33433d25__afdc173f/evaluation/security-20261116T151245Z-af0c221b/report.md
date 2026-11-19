# Security Audit — stage-05 run afdc173f — release/000001

## Audit narrative

### Profile (Phase 1)
A 82-line C++ multi-threaded HTTP server. Relevant surface: alias prefix override, an If-None-Match and Range path, and a proxying upstream path. Because it is a reverse
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
reach the upstream and splits its request line (`evidence/ev_qkv_1cfd33433d25__afdc173f.log`, case `query CRLF`, alongside
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
| SEC-002 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 50 (`recv`) |
| SEC-003 | Space in the path defeats the `c<32` control-byte guard and splits the upstream request line | request smuggling | yes | medium | line 56 (`decode`), forwarded at line 80 (`path`) |
| SEC-004 | Query string is forwarded undecoded and unvalidated, so `%0d%0a` in the query splits the upstream request line where the path guard would reject it | request smuggling | yes | high | line 56 (`decode(`): `query` from raw target, appended without re-validation |
| SEC-005 | An interim (1xx) upstream response is emitted as terminal with no body, and the real response is discarded | response framing | yes | low | line 80 (`st>=100&&st<200`) |
| SEC-006 | `Expect: 100-continue` is not special-cased, and the client waiting for 100 is finally answered 408 | HTTP conformance / availability | yes | low | parser, no `expect` handling |
| SEC-007 | `SIGTERM` drain ends at exactly `drain_timeout_ms` with 0 body bytes written for the in-flight proxied response | graceful shutdown / availability | yes | medium | `drain_timeout_ms` bounds the wait, not completion of the response |
| SEC-008 | `Transfer-Encoding: gzip, chunked` is rejected as a 400 because the whole field value is compared against `chunked` | HTTP conformance / interop | yes | low | line 64 (`lower(trim(te[0]))!="chunked"`) |
| SEC-009 | The smuggled exec response is cached under the attacker's own key, so one request installs a server-generated page served to every later client | cache poisoning + RCE persistence | yes | high | line 75 (`cachebase`) |

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

The header loop returns the moment `\r\n\r\n` is found (line 50 (`recv`) and line 69 (`close`)) and never drains bytes the
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
renders `Location` from the pre-decode `raw` target, so even a decoded control byte would not reach
the header. Measured, `evidence/split_negative.log`:

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
line is rebuilt from the decoded path at line 80 (`path`), so the line becomes:

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

The proxy decodes `%20` to a space — the guard at line 56 (`decode`) only tests
`<32`, so `0x20` passes — forwards the decoded path unchanged, and the upstream parses:

```
GET /exec ?cmd=id HTTP/1.1
```

and answers `200` with `uid=1000(mouse9911) …`. Evidence `evidence/ev_space_afdc173f.log` is the captured exchange:
the client bytes, the upstream head exactly as the upstream parsed it, and the returned body.

Severity **medium**: single request, no authentication, no memory safety needed — but it requires
the upstream to split the request line on whitespace and to have an executing route on the
target. A strict upstream that splits on single spaces only and rejects extra tokens is unaffected.

### SEC-004 — the query string bypasses the control-byte guard and splits the upstream line

The decode loop guards the **path** and nothing else. The target is split on `?` first
(line 56), the query is taken from the *raw* string, and only the pre-`?` part is walked
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

Measured (`evidence/ev_qkv_1cfd33433d25__afdc173f.log`): the query CRLF payload returns `200` with `uid=…`; the bare-LF form
(`%0a`, no CR byte) works identically; and the path-CRLF control case still answers `400` with no
upstream connection, which is the contrast this finding turns on.

Severity **high**: one unauthenticated request, no memory-safety primitive, reaching whatever the
upstream executes. Preconditions are the proxying location this run already has enabled plus an
upstream that decodes then splits.

### SEC-005 — a 1xx is emitted as terminal and the real response is thrown away

The body-suppression test here already includes the interim range (`st>=100&&st<200`, line 80), so a
`1xx` is treated as bodyless — but it is still written out as **the** response, with
`Connection: close`, and the final answer is then discarded when the upstream closes.

Measured (`evidence/ev_1xx_1cfd33433d25__afdc173f.log`): an upstream answering `103 Early Hints` then `200 OK` / `HELLO` gives

```
HTTP/1.1 103 Error
link: </s.css>; rel=preload
Content-Length: 0
Connection: close
```

with zero payload bytes, so the client waits for a final response that never arrives. `HELLO`
never reaches it.

Severity **low**: same reachability impact as the harder 502 form, but the connection is closed
cleanly, so a client that retries is not wedged.

Fix: `continue` on `1xx` instead of falling through to the emit path.

### SEC-006 — `Expect: 100-continue` is not special-cased, and the wait ends in 408

`Expect` is not recognised here. The head is accepted and the body drain waits, so a correct client
that is holding the body until it sees `100` gets nothing Expect is not special-cased; the stalled body trips the read deadline and yields 408.

Measured (`evidence/ev_expect_1cfd33433d25__afdc173f.log`): after the wait the client receives

```
HTTP/1.1 408 Request Timeout
Content-Length: 0
Connection: close
```

The control without `Expect` is `200` in the same log.

Severity **low**: the request fails cleanly, but an upload that would have succeeded without the
standard header is refused purely because the client was polite. Fix: emit `100 Continue` on
`Expect` before draining.

### SEC-007 — drain truncates the proxied response at zero bytes

`operations.md:7` requires in-flight responses to be finished up to `drain_timeout_ms`. The deadline
is respected exactly, and the response is truncated exactly there:

```
upstream delay 5.0 s, drain_timeout_ms 2000, SIGTERM at t+0.3 s
-> closed at +2.01 s with 0 of 10 body bytes, master exited +2.11 s
```

Reproduced 2/2. The deadline terminates the wait rather than bounding completion, so a slow upstream
always loses the response. The shutdown itself is bounded and prompt, so medium.

Reload is unaffected — SIGHUP switches the root and the master survives
(`evidence/ev_s5_lifecycle_all.log`).

### SEC-008 — `Transfer-Encoding: gzip, chunked` is rejected instead of being treated as chunked

`proxy.md:4` permits `Transfer-Encoding: chunked` and requires unsupported codings to be rejected. The
parser here compares the **entire** field value against the literal `chunked` (line 64 (`lower(trim(te[0]))!="chunked"`)), so any coding
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

The cache key is built from `"http://"` + host + the **raw target** (line 75 (`cachebase`)) — exactly the
string the smuggle operates on, with no record that the answer came from a second request. The store
function accepts the entry because the upstream answered `public, max-age=60`, and the lookup function
then serves it without contacting the upstream. Nothing in the key or the stored value
records that the response came from a *second*, smuggled request, so the smuggled `/exec` output is
filed as the canonical answer to the attacker's `/api/x?...` URL.

Consequence: the smuggling is not per-request. One unauthenticated request both executes the command
and **installs** the result as a cached page for anyone who subsequently requests that URL, for the
whole TTL. A victim does not need to craft anything and the upstream is not touched again.

Measured (`evidence/ev_cache_rce_afdc173f.log`), count of upstream connections across two identical requests:

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

- `evidence/ev_cache_rce_afdc173f.log` — smuggled exec output cached: 1 upstream hit, `uid=` served twice.

| File | Purpose |
|---|---|
| `evidence/rce_probe.log` | Encoded-CRLF smuggling cases against the code-executing upstream |
| `evidence/rce_probe_prod.log` | Same, production build |
| `evidence/smuggle_probe.log` | Strict byte-parsing upstream; confirms the decoded CRLF never reaches the wire |
| `evidence/isolation_probe.log` | Control isolation: `%70` and plain both forward 200; only control bytes refused |
| `evidence/upstream_malformed.log` | Malformed-upstream response cases |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
| `evidence/ev_space_afdc173f.log` | Decoded space in the path reaching the upstream request line; upstream head captured |
| `evidence/ev_s5_lifecycle_all.log` | Stage-05 lifecycle matrix: drain timing per build, idle hang, reload baseline |
| `evidence/ev_s5_hang_threads.log` | /proc thread dump 2 s after SIGTERM: 33 threads parked in futex_do_wait, listener already closed |
| `evidence/ev_techain_all2.log` | Coding-chain matrix, five kv builds: every single-token form forwards 200, both chains 400 |
`evidence/ev_expect_1cfd33433d25__afdc173f.log` | `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control |
`evidence/ev_1xx_1cfd33433d25__afdc173f.log` | Upstream interim response (103, then 200): control with no interim response, then 100/102/103 |
`evidence/ev_qkv_1cfd33433d25__afdc173f.log` | Query-only CRLF and bare-LF split against a line-oriented decoding upstream, with the path-CRLF control case |
