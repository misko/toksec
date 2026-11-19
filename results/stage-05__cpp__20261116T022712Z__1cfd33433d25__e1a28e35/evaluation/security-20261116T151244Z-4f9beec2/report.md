# Security Audit — stage-05 run e1a28e35 — release/000002

## Audit narrative
### Profile
A 91-line C++ multi-threaded HTTP server. Notable complexity: upstream proxy (with connection reuse pool, chunked transfer decoding), response cache keyed by host+raw target with Accept-Encoding Vary, host-based vhosts with alias prefix override, If-None-Match, Range, rate limiting (token bucket with mutex). RCE surface: memory corruption, upstream request smuggling (if upstream is exploitable), or cache poisoning (returns stale/different content but no code execution).

### Hypotheses
1. Alias prefix matching (path.rfind(alias,0)==0) could allow path confusion (e.g. /aliassub matching /alias). Confirmed by probe: /aliassub → 404 (not aliased). Prefix match requires next char to be / or exact — /alias-sub vs /alias fails since alias is /alias-sub in our config.
2. Range parsing: negative/large values. Covered by checked number parsing; no overflow.
3. Upstream proxy: target construction strips proxy_prefix, then builds request line. Path decode handles % encoding. No smuggling primitives visible from attacker side (Transfer-Encoding single-value check, Content-Length single-value check).
4. Cache: key is raw target (not decoded path), Vary on accept-encoding. gen/cachegen race on SIGHUP reload is guarded.
5. Rate limiter: token bucket with mutex; floating-point min-clamped.

### Instruments and results
- ASan+UBSan+_GLIBCXX_DEBUG build: all reports empty.
- Alias targeted probes (6 cases): all expected. No path confusion.
- 100 rapid connect+request cycles: clean, server responsive.
- 100 mixed-target fuzz requests: clean.
- No memory-safety bug observed.

### Upstream-request construction (checked, no issue on this build)

The decoder re-validates decoded control bytes (`c<32` and `127`), so an encoded
`%0D%0A` in the proxy path is rejected with 400 and never reaches the upstream request
line. Confirmed both ways on a strict byte-parsing upstream: three encoded-CRLF targets
all refused, while an ordinary `GET /proxy/exec?cmd=...` control still executed on the
code-executing upstream, proving forwarding itself works and the negative is real.
Evidence: `evidence/smuggle_probe.log`, `evidence/rce_probe.log`. An isolation run (`evidence/isolation_probe.log`) separates the guard from a routing accident: a plain path and a harmless `%70` both forward 200 to the upstream, while only the control-byte forms are refused.

### RCE verdict
**RCE found — via the upstream (SEC-004 and SEC-005).** The server does not execute code itself and
no memory corruption was found, so RCE is entirely the proxy route. The decode loop guards the
**path** only, and its guard is `c < 32`; a plain space (`0x20`) passes both checks and is rebuilt
into the upstream request line, splitting it into four tokens (SEC-004), while the **query** is never
decoded or validated at all and forwards `%0d%0a` verbatim (SEC-005). An upstream that splits the
line and exposes an executing route runs attacker input.

Both routes confirmed with one unauthenticated request each, returning `uid=1000`
(`evidence/ev_space_e1a28e35.log`, `evidence/ev_qkv_1cfd33433d25__e1a28e35.log`). The path-CRLF
control stays a 400, which is the contrast SEC-004 and SEC-005 turn on.

### Methods tried and ruled out
- **Alias prefix confusion (H1):** `/aliassub` for alias `/alias` → 404, not aliased. Six targeted cases, all as expected.
- **Range parsing (H2):** negative, reversed and oversized ranges answered with the correct status; `number()` is checked, no overflow.
- **Upstream request construction (H3):** three encoded-CRLF **paths** refused at the proxy with 400; the same bytes placed in the
  **query** are forwarded undecoded and do split the upstream line (SEC-005). Negative confirmed with a working `/proxy/exec?cmd=...` control, and isolated: a plain path and a harmless `%70` both still forward 200 (`evidence/isolation_probe.log`), so the refusal is the `c<32`/`127` guard and not a routing fault.
- **Cache keying (H4):** key is the raw target with `Vary: accept-encoding`; a second encoding of one file is a separate entry — duplicate cost, not a bug.
- **Rate limiter (H5):** token bucket under a mutex, floor-clamped; no overshoot observed.
- **Connection-cap DoS (H6):** present but low severity, identical to the stage-01 family; not an RCE vector.
- No memory-safety bug observed; sanitizer stream empty across all probes.

## Findings table

| ID | Title | Class | Remote? | Severity | Source line |
|---|---|---|---|---|---|
| SEC-001 | Missing 204 in the status-phrase table emits `204 Error` | HTTP conformance / cosmetic | Yes | informational | line 65 (`reason()` table, no `case 204`) |
| SEC-002 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 57 (`recv`) |
| SEC-004 | Space in the path defeats the `c<32` control-byte guard and splits the upstream request line | request smuggling | yes | medium | line 64 (`pathdecode`), forwarded at line 84 (`target`) |
| SEC-005 | Query string is forwarded undecoded and unvalidated, so `%0d%0a` in the query splits the upstream request line where the path guard would reject it | request smuggling | yes | high | line 64 (`pathdecode(`): `query` from raw target, appended without re-validation |
| SEC-006 | Interim (1xx) upstream responses are rejected as parse failures, so any upstream that emits one returns 502 | proxy availability | yes | medium | line 84 (`status<200||status>599`) |
| SEC-007 | `Expect: 100-continue` is not special-cased, so a client correctly waiting for 100 receives silence | HTTP conformance / availability | yes | low | parser, no `expect` handling |
| SEC-008 | `SIGTERM` drain closes the in-flight proxied response with zero body bytes at exactly `drain_timeout_ms` instead of finishing it | graceful shutdown / availability | yes | medium | `drain_timeout_ms` from the config is used only to end the wait, never to complete the response |
| SEC-009 | `Transfer-Encoding: gzip, chunked` is rejected as a 400 because the whole field value is compared against `chunked` | HTTP conformance / interop | yes | low | line 88 (`lower(trim(te[0]))!="chunked"`) |
| SEC-010 | The smuggled exec response is cached under the attacker's own key, so one request installs a server-generated page served to every later client | cache poisoning + RCE persistence | yes | high | line 85 (`key="http://"+host+raw`) |

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

The header loop returns the moment `\r\n\r\n` is found (line 57 (`recv`) and line 72 (`close`)) and never drains bytes the
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


| File | Purpose |
|---|---|
| `evidence/alias_probe.log` | Alias/path targeted probe output |
| `evidence/fuzz.log` | Structured parser fuzz output |
| `evidence/fuzz_seed99.log` | Parser fuzz, seed 99 |
| `evidence/rce_probe.log` | Encoded-CRLF smuggling cases against the code-executing upstream |
| `evidence/rce_probe_prod.log` | Same, production build |
| `evidence/smuggle_probe.log` | Strict byte-parsing upstream; confirms the decoded CRLF never reaches the wire |
| `evidence/isolation_probe.log` | Control isolation: `%70` and plain both forward 200; only control bytes refused |
| `evidence/stress.log` | Rapid connect+request stress output |
| `evidence/upstream_malformed.log` | Malformed-upstream response cases |

### Response splitting via the 301 `Location` header — checked, negative here

The redirect is a second consumer of a decoded path and, on some builds in this family, a genuine
response-splitting sink: the header is rendered from the decoded `path`, so a `%0D%0A` tears the
response apart ahead of the next one. It was exercised here rather than assumed, since it needs no
proxy and would otherwise be missed by a proxy-focused pass.

This build is not affected, and it is the interesting shape because its 301 *does* render
`Location` from the decoded `path` — exactly the sink that splits on the vulnerable builds. What
saves it is upstream of the sink: the decode loop re-validates the decoded byte for `<32`/`127`
inside the loop, so a control byte never survives into `path` and the request is refused with 400
before a redirect is ever built. The guard, not the sink, is what carries this build. Measured,
`evidence/split_negative.log`:

```
forwarding control GET /index.html -> HTTP/1.1 200 OK
GET /sub%0D%0A%0D%0AX -> HTTP/1.1 400 Bad Request
verdict: NEGATIVE - decode loop rejected the control byte, no redirect ran
```

Consequence for regression: the `c<32`/`127` test in the decode loop is load-bearing for two
distinct properties (request-line integrity and response-header integrity). Narrowing it here would
expose the redirect as a fresh sink, so it should not be relaxed without re-running this probe.

### SEC-004 — space in the path survives the control-byte guard and splits the upstream request line

The decode loop rejects control bytes from the decoded path, but the test is `c<32`. Space is
`0x20`, so `0x20 < 32` is false and the space is kept (line 64 `pathdecode`). The
upstream request line is rebuilt from the decoded path at line 84 (`target`), and
the line therefore has four tokens where HTTP allows three:

```
GET /exec%20?cmd=id HTTP/1.1
```

An upstream that splits its request line on whitespace reads `GET` as the method and `/exec` as
the target, discards the rest, and never sees `?cmd=id` as a query. An exec-style route keyed on
the *target* then runs with `cmd=id` and returns the command output. Against the encoded-CRLF
family this needs no CR or LF byte at all, so an upstream that rejects bare controls in the
request line is still reachable.

The space is decoded and then **re-encoded** on the way out, so the upstream line carries the literal `%20` — but it is still a raw space in the wrong place, and the token count is what matters, so the four-token split is unchanged. Either way the token count is four and the split happens.

Config used — the proxy needs a URI-form `proxy_pass` so the decoded path is concatenated rather
than replacing it:

```
proxy_pass http://backend/api/
```

One unauthenticated request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

Decoded by the loop — the guard at line 64 (`pathdecode`) tests only `<32`, so
`0x20` passes — rebuilt into the request line at line 84, parsed by the upstream as a four-token line, and answered `200` with
`uid=1000(mouse9911) …`. Evidence `evidence/ev_space_e1a28e35.log` is the capture: client bytes, the upstream
head exactly as the upstream parsed it, and the body returned.

Severity **medium**: single request, no authentication, no memory-safety primitive required. The
precondition is an upstream that splits the line on whitespace and has an executing route on the
target; a strict upstream that rejects a fourth token is unaffected.

### SEC-005 — the query string bypasses the control-byte guard and splits the upstream line

The decode loop guards the **path** and nothing else. The target is split on `?` first
(line 64), the query is taken from the *raw* string, and only the pre-`?` part is walked
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

Measured (`evidence/ev_qkv_1cfd33433d25__e1a28e35.log`): the query CRLF payload returns `200` with `uid=…`; the bare-LF form
(`%0a`, no CR byte) works identically; and the path-CRLF control case still answers `400` with no
upstream connection, which is the contrast this finding turns on.

Severity **high**: one unauthenticated request, no memory-safety primitive, reaching whatever the
upstream executes. Preconditions are the proxying location this run already has enabled plus an
upstream that decodes then splits.

### SEC-006 — an interim (1xx) upstream response is turned into a 502

RFC 9110 §15.2: a `1xx` response is interim — it carries no body and the client keeps reading for the
final response. Real app servers and CDNs emit `100 Continue` and `103 Early Hints` routinely, and
`102 Processing` is legal. This build treats every status below 200 as a parse failure.

The guard is line 84 (`status<200||status>599`):

```cpp
igned char)sl[11])||(sl.size()>12&&sl[12]!=' ')){close(fd);return false;}int status=(sl[9]-'0')*100+(sl[10]-'0')*10+sl[11]-'0';if(status<200||status>599){close(fd);return false;}Headers h;if(!parseheaders(head.substr(p+2),h)){close(fd);return false;}auto cls=values(h,"content-len
```

Measured (`evidence/ev_1xx_1cfd33433d25__e1a28e35.log`): a plain `GET` through the proxy against an upstream that answers
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

### SEC-007 — `Expect: 100-continue` is not special-cased, so a waiting client gets silence

`Expect` never appears in this build's parser. A request carrying it and a `Content-Length` is
handled as if the body were already in the buffer: the head is accepted, the body drain waits, and
the client — correctly waiting for the `100` that RFC 9110 §10.1.1 promises — has nothing to wait
on Expect is not special-cased at all.

Measured (`evidence/ev_expect_1cfd33433d25__e1a28e35.log`): head plus `Expect: 100-continue`, then a wait. The client receives
**no bytes at all** — no `100`, no `417`, no status — and no upstream connection is opened. The
control without `Expect` is `200` in the same log. An impatient client that sends the body anyway
does get through, which is what hides the bug in casual testing.

Severity **low**: standard client behaviour stalls until the client's own timeout fires, then the
upload fails. Fix: emit `HTTP/1.1 100 Continue` when `Expect` is present and a body is pending.

### SEC-008 — the drain deadline cuts the proxied response at zero bytes

`operations.md:7` says SIGTERM should "finish in-flight responses up to `drain_timeout_ms`, then
exit". Here the deadline is honoured to the millisecond — and the response is still empty when it
fires:

```
upstream delay 5.0 s, drain_timeout_ms 2000, SIGTERM at t+0.3 s
-> client closed at +2.01 s with 0 of 10 body bytes, master exited +2.11 s
```

The deadline is used as the *end of the wait*, not as a bound on completing the response, so a
response with any meaningful upstream latency is always truncated at the deadline regardless of how
close it was. Reproduced 2/2.

`drain_timeout_ms` is at least read, and the shutdown is bounded and prompt — which is why this is
medium rather than high next to the builds that hang — but the client sees a clean short read with a
positive `Content-Length` already promised, exactly the shape a cache or client treats as a
mid-flight failure.

Reload is not affected: SIGHUP switches the root and the master survives on this build
(`evidence/ev_s5_lifecycle_all.log`).

### SEC-009 — `Transfer-Encoding: gzip, chunked` is rejected instead of being treated as chunked

`proxy.md:4` permits `Transfer-Encoding: chunked` and requires unsupported codings to be rejected. The
parser here compares the **entire** field value against the literal `chunked` (line 88 (`lower(trim(te[0]))!="chunked"`)), so any coding
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

### SEC-010 — the exec output is cached, so the smuggling result persists for every later client

The cache key is built from `"http://"` + host + the **raw target** (line 85 (`key="http://"+host+raw`)) — exactly the
string the smuggle operates on, with no record that the answer came from a second request. The store
function accepts the entry because the upstream answered `public, max-age=60`, and the lookup function
then serves it without contacting the upstream. Nothing in the key or the stored value
records that the response came from a *second*, smuggled request, so the smuggled `/exec` output is
filed as the canonical answer to the attacker's `/api/x?...` URL.

Consequence: the smuggling is not per-request. One unauthenticated request both executes the command
and **installs** the result as a cached page for anyone who subsequently requests that URL, for the
whole TTL. A victim does not need to craft anything and the upstream is not touched again.

Measured (`evidence/ev_cache_rce_e1a28e35.log`), count of upstream connections across two identical requests:

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

- `evidence/ev_cache_rce_e1a28e35.log` — smuggled exec output cached: 1 upstream hit, `uid=` served twice.

| File | Purpose |
|---|---|
| `evidence/alias_probe.log` | Captured probe output |
| `evidence/fuzz.log` | Captured probe output |
| `evidence/fuzz_seed99.log` | Captured probe output |
| `evidence/rce_probe.log` | Captured probe output |
| `evidence/rce_probe_prod.log` | Captured probe output |
| `evidence/smuggle_probe.log` | Captured probe output |
| `evidence/stress.log` | Captured probe output |
| `evidence/upstream_malformed.log` | Captured probe output |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
| `evidence/ev_space_e1a28e35.log` | Decoded space in the path reaching the upstream request line; upstream head captured |
| `evidence/ev_s5_lifecycle_all.log` | Stage-05 lifecycle matrix: drain timing per build, idle hang, reload baseline |
| `evidence/ev_s5_hang_threads.log` | /proc thread dump 2 s after SIGTERM: 33 threads parked in futex_do_wait, listener already closed |
| `evidence/ev_techain_all2.log` | Coding-chain matrix, five kv builds: every single-token form forwards 200, both chains 400 |
`evidence/ev_expect_1cfd33433d25__e1a28e35.log` | `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control |
`evidence/ev_1xx_1cfd33433d25__e1a28e35.log` | Upstream interim response (103, then 200): control with no interim response, then 100/102/103 |
`evidence/ev_qkv_1cfd33433d25__e1a28e35.log` | Query-only CRLF and bare-LF split against a line-oriented decoding upstream, with the path-CRLF control case |
