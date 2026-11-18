# Security Audit — stage-10 run 063b0d5e — release/000002

## Identity

- Run: `stage-10__cpp__20261116T022716Z__1cfd33433d25__063b0d5e`
- Analyzed tag: `release/000002` (2 releases; 000002 = final)
- Commit: `80867f23fd76ced38153728f6a813c082ae4a9d1`
- Source: `main.cpp`
- SHA-256: `e5cd16c196af595f92eab5b202fb1430d064a201c3e8b1c79ebd61e8104a61c5` (82 lines)
- Server: nginx-subset HTTP/1.1 server; `fork()` workers, `poll()` event loop, `sendfile.h` included, non-blocking upstream relay with a state-machine chunked decoder, 64 MiB response cap

## Audit narrative

### Profile (Phase 1)

82-line C++ nginx subset with a `poll()`-driven, connection-object state machine (`struct Conn` carrying `ufd`, `uheaders`, `ufinished`, `chunkstate`, `chunkleft`, `respleft`, `downstream_chunked`, `upstream_chunked`, `reqleft`). Static reads use `pread()` into a `std::string body(length, '\0')` after a 64 MiB `length` cap (`if(length>67108864){…fail(403)}`). Responses are assembled in `c.out` and flushed non-blockingly with a `sent` cursor.

The distinguishing component is the **upstream relay**: `upstream_parse()` implements a resumable HTTP/1.1 parser for the upstream response, including interim 1xx handling (max 8), duplicate `Content-Length`/`Transfer-Encoding` rejection, hop-by-hop header filtering driven by the upstream `Connection` header, chunk-size parsing with overflow guard (`n > (ULLONG_MAX>>4)`), per-chunk 64 MiB limit, optional downstream re-chunking for HTTP/1.1 clients, and a `131072`-byte write-queue backpressure gate.

Notable divergence: this build answers traversal with **400** rather than 403.

No CGI, no `system()`, no `popen()`, no `exec*()`.

**RCE surface: memory corruption only.** The upstream state machine is the largest new parsing surface, so it gets the most weight.

### Hypotheses (Phase 2)

1. Chunked-decoder state confusion: split chunk headers, chunk ext after `;`, `\r\n` split across reads, trailer handling, `n` overflow, zero-size final chunk.
2. `c.out.size() - c.sent` arithmetic if `sent` ever exceeds `size` (unsigned underflow → huge backpressure window).
3. Interim (1xx) response loop and the `chunkstate > 8` guard.
4. `stoll` on upstream `Content-Length` and on request `Range`.
5. Header-count blowup in upstream responses (`manycl`, `te_identity`).
6. 64 MiB cap boundary: exactly 64 MiB, 64 MiB+1, and ranges that start at the boundary.

### Instruments (Phase 3)

Full harness family against `target-san`, including the malformed-upstream and upstream-fuzz suites that specifically target the chunked decoder.

Sustained-load and allocator-aware probes were added on top of the harness family: a 4-worker soak (4 forked workers, `nginx_mw.conf`) serving 5,000 sequential keep-alive requests against the production build with fd sampling, 20,000 keep-alive requests against the ASan build, and 20,000 new connections against both builds to separate real growth from allocator quarantine.

### Results and ruled-out hypotheses

Zero sanitizer output; every `srv*.log` empty.

- **Chunked decoder (H1):** 15 malformed upstream modes (no headers, garbage, empty status, huge status, bad header, CL+chunked, long header, many Content-Length, `te: identity`, none) all either relayed correctly or 502'd; upstream fuzzing 3 × 500 = 1500 iterations clean.
- **Backpressure arithmetic (H2):** no crash across lifecycle/backpressure phases.
- **1xx loop (H3):** guard present and exercised only by fuzzing; no anomaly.
- **`stoll` (H4):** range overflow shapes → 400; upstream `Content-Length` non-numeric → 502.
- **Header blowup (H5):** several duplicate/oversized upstream headers handled without crash.
- **64 MiB cap (H6):** exactly 64 MiB served with 200 and full length; 64 MiB+1 and 80 MiB correctly rejected with **403**; ranges anchored exactly at 67,108,864 returned the correct remainder (16,777,216 bytes) with 206.

- **TLS handshake parsing (H7):** a self-signed RSA-2048 certificate was configured and the custom `sni_cb`/`alpn_cb` callbacks were driven with 32 adversarial ClientHellos (extension declared-length mismatches, oversize/zero-length ALPN entries, 255-byte names, 250-name SNI lists, duplicated and malformed extensions, wrap-around record lengths) plus 600 crafted fuzz iterations. A valid handshake with SNI `localhost` and ALPN `http/1.1` returns 200 with the expected body; every adversary produced only TLS alerts (handshake_failure) and no sanitizer output.

- **Sustained load and memory (H8):** 5,000/5,000 keep-alive requests succeeded across 4 forked workers on the production build, with no failures, empty server logs, and fds flat at 4 → 4; 20,000 further keep-alive requests were clean on the ASan build. Over 20,000 new connections production RSS showed 0kB growth after warmup, while the ASan build climbed 13,572kB — allocator quarantine retention, not a leak. No connection-cap ceiling (`ECONNREFUSED`/dropped accepts) appeared at these levels.

### RCE verdict

**RCE found — via the upstream (SEC-003).** No local exec component and no memory corruption across
~12,000 fuzz iterations, so RCE is entirely the proxy route. The decoder re-validates `c < 32` and
`127` after decoding, which kills the encoded-CRLF form used against the siblings; but the guard is
`c < 32`, so a plain space (`0x20`) survives, is rebuilt into the upstream request line, and splits
it. An upstream that splits the line on whitespace and executes the target runs attacker input.
Confirmed with one unauthenticated request returning `uid=1000`
(`evidence/ev_space_063b0d5e.log`), and again with a bare `proxy_pass`
(`evidence/ev_bare_063b0d5e.log`).

This build is also the least reachable of the family: SEC-005 makes any request carrying a
`Content-Length` a 400, so the body-replay route cannot be used here and the space split is the only
execution path.

## Findings table

| ID | Title | Class | Remote? | Severity |
|---|---|---|---|---|
| — | No defects found within scope for memory safety | — | — | — | decoder lines 63/82 checked; `pathnorm()` line 47 |
| SEC-001 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low |
| SEC-003 | Space in the path defeats the `c<32` guard and splits the upstream request line | request smuggling | yes | medium | line 47 (`pathnorm`), forwarded at line 58 (`upath`) |
| SEC-004 | Split also works with a bare `proxy_pass`, no URI needed | request smuggling | yes | medium | rebuild at line 58 (`upath`), guard line 47 (`pathnorm`) |
| SEC-005 | `h.count("transfer-encoding")` is evaluated after `h["transfer-encoding"]` already inserted the key, so any request with a `Content-Length` is answered 400 | request framing | yes | high | line 53, `h["transfer-encoding"]` |
| SEC-006 | `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected | HTTP conformance / availability | yes | low | line 50 (`if(h.count("expect"))`) |
| SEC-007 | `Transfer-Encoding: chunked` request bodies are refused with 400, so every standard chunked upload fails | HTTP conformance / availability | yes | medium | line 55 (`fail(400)`): `if(!h["transfer-encoding"].empty()){fail(400);return;}` |
| SEC-008 | A legal upstream `Transfer-Encoding` + `Content-Length` pair is rejected with 502 | HTTP conformance / availability | yes | medium | line 69 (`upstream_fail(c,502)`): `(!fields["content-length"].empty()&&!fields["transfer-encoding"].empty())` |
| SEC-009 | The reason-phrase table has no entries between `206` and `301`, so `203`, `204` and `205` are relabelled `Service Unavailable` | HTTP conformance / status corruption | yes | low | line 41 (`reason`): `default:return "Service Unavailable";` |
| SEC-010 | `SIGTERM` never terminates an idle server: the master blocks in `waitpid` and the handler is restartable, so `stopping` is set but never observed | graceful shutdown / availability | yes | medium | line 82 (`waitpid`): `pid_t p=waitpid(-1,&status,0)` |
| SEC-015 | Chunk-size fields longer than 16 chars, `0x`-prefixed, or space-prefixed are rejected mid-response, leaving a 200 with `TE: chunked` and an empty unterminated body (`IncompleteRead`); unique to this build | HTTP conformance / response integrity | yes | medium | size cap and strict hex in the chunk decoder: `if(v.empty()||v.size()>16)` |


### Proxy smuggling — checked, negative on this build

A smuggling-to-RCE test was run against this build because the sibling builds in this stage
expose it. This one is **not** vulnerable: its decoder rejects `c<32` and `127`, so a decoded CR/LF never reaches
the path and the upstream request line stays clean.

Proven with the same harness that succeeds elsewhere: a controlled upstream echoes the request
head it parsed, a normal proxied object returns 200, and both encoded-CRLF forms return 400
before any upstream request is emitted. The negative is therefore a decoder difference, not a
harness or configuration artifact.


### Upstream-request construction (checked, no issue on this build)

The decoder re-checks the decoded byte for `c < 32` and `127` before use, so the upstream request line cannot carry CR/LF. Verified live with the same harness that succeeds on the three vulnerable builds: both encoded-CRLF forms answer 400 with no upstream request emitted (`evidence/smuggle_rce.log`).

### The exploit (checked, negative)

**Classification:** no exploitable defect on this build for the proxy route; the finding set stays
as listed above.

**What was attempted** — the encoded-CRLF smuggling forms proven on the sibling builds, in both the
header-injection and injected-second-request shapes, driven into this build against a strict
byte-parsing upstream.

**Verified output:** both forms answer `400` and the upstream receives no request.

**Configuration requirement:** the negative holds for any configuration — it is the decoder, not
the runner, that rejects the bytes, so enabling `proxy_pass` with a URI does not change it.

### Fix (not required on this build, but worth pinning)

Nothing to fix here — the decoder already rejects `c < 32` and `127` after decoding. Pin it with a
regression test so a future rewrite cannot silently drop the check: keep
`/%2Fexec%3Fcmd%3Did%0D%0AX:%201` as a case and assert 400 plus no upstream request, the inverse
of the assertion the vulnerable siblings need.

## Notes for future agents

1. This build applies a 64 MiB cap with `403` and is the only stage-10 run whose traversal answer is `400`. Both are intentional-looking but non-nginx behaviors; check them against the stage spec before treating them as bugs.
2. `emit()` re-chunks upstream chunks for HTTP/1.1 clients using a 32-byte `snprintf` buffer — correct today because `%zx` of a ≤64 MiB value fits, but a cap increase would need a bigger buffer.
3. `c.out.size()-c.sent<131072` gates all relay writes; unsigned underflow here would be a serious bug class. Worth a targeted invariant test on any future refactor.

### Response splitting via the 301 `Location` header — checked, negative here

The redirect path is the second consumer of a decoded path, and on some builds in this family it is
a genuine response-splitting sink: the header is rendered from the decoded `path`, so a `%0D%0A`
in the request tears the response apart ahead of the next one. It was checked here rather than
assumed.

This build is not affected. Its decode loop re-validates the decoded byte for `<32`/`127` inside
the loop, so a control byte never survives into `path` and the request is refused with 400 before a
redirect is ever built. The sink itself is still fed the decoded path (`Location: "+path+"/"+query`),
so the gate is the decoder, not the sink. Measured, `evidence/split_negative.log`:

```
GET /sub%0D%0A%0D%0AX -> HTTP/1.1 400 Bad Request
HTTP response starts: 1
verdict: 400 Bad Request before any redirect, decoded path already clean -> no split
```

Consequence for regression: if the `c<32`/`127` check is ever narrowed here, the redirect becomes a
splitting sink immediately, so the existing check is load-bearing for two distinct properties
(request-line integrity and response integrity) rather than one.

### SEC-001 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 76 (`recv`) and line 80 (`close`)) and never drains bytes the
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

### SEC-003 — space in the path survives the control-byte guard and splits the upstream request line

Decoding accepts a percent-encoded space. The guard that would reject a control byte is written
`c<32`, and space is `0x20`, so `0x20 < 32` is false and the space survives (line 47 `pathnorm`).
The upstream request line is rebuilt from the decoded path at line 58 (`upath`), so it carries
four tokens where HTTP allows three:

```
GET /exec ?cmd=id HTTP/1.1
```

An upstream that splits its request line on whitespace takes `GET` and the target, drops the rest,
and never treats `?cmd=id` as a query. An exec route keyed on the target then runs `cmd=id`. This
needs no CR or LF byte, so it also reaches upstreams that reject bare controls in the request
line. Config: URI-form `proxy_pass http://backend/api/`.

One unauthenticated request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

answers `200` with `uid=1000(mouse9911) …`. Evidence `evidence/ev_space_063b0d5e.log` captures the client bytes,
the upstream head exactly as the upstream parsed it, and the returned body.

Severity **medium**: single request, unauthenticated, no memory-safety primitive. Precondition is
an upstream that splits the line on whitespace with an executing route on the target; a strict
upstream that rejects a fourth token is unaffected.

### SEC-004 — the split also works with a bare `proxy_pass`, no URI needed

`proxy_pass http://backend` with no URI and no trailing slash still rebuilds the upstream request
line from the decoded path at line 58 (`upath`), so the decoded space still yields four tokens:

```
GET /api/exec%20?cmd=id HTTP/1.1
```

A bare `proxy_pass` does not decode, so the proxy forwards the target verbatim and the line is a
literal `%20` on the wire. The split then happens in the **upstream's own target decoding**: it
unquotes `%20` to a space first and splits the resulting four tokens, taking `GET` / the target and
dropping `?cmd=id` from the query slot. Precondition is narrower than the URI form (the upstream
must decode the target, not merely split on whitespace) but the config surface is wider, because
any proxying location qualifies rather than only a URI-form one.

This widens the primitive to any proxying location: the URI-form `proxy_pass` seen elsewhere in
this family is not required. The line guard at 47 (`pathnorm`) still admits `0x20` because it only
tests `<32`. One request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

answers `200` with `uid=1000(mouse9911) …`. `evidence/ev_bare_063b0d5e.log` records the bare config, the upstream
head exactly as parsed, and the returned body. Severity **medium**: same class, wider config surface.

### SEC-005 — the header check rejects every request that carries a `Content-Length`

Line 53 tests three things, and the third one is self-defeating:

```cpp
if(h["content-length"].size()>1||h["transfer-encoding"].size()>1||(h.count("transfer-encoding")&&!h["content-length"].empty())){fail(400);return;}
```

`h` is a `std::map` and the first two clauses use `operator[]`, which **default-inserts** a missing
key. By the time the third clause is evaluated, `h` contains `transfer-encoding` even when the
client never sent one, so `h.count("transfer-encoding")` returns `1` while
`h["transfer-encoding"].size()` returned `0` — the exact inconsistency visible in the debug run:
`a1=0 a2=0 a3=1 cl1=1 te1=0 count=1`.

The intent was "reject TE with a body length". The effect is "reject any `Content-Length` at all",
because the count is 1 by construction. Both the proxy block (line 52, returns immediately) and the
static path (line 61 re-tests a similarly shaped condition) sit behind it.

Measured (`evidence/ev_cl_063b0d5e.log`):

| request | result |
|---|---|
| `GET /api/x`, no CL | `200 OK`, one upstream connection |
| `Content-Length: 0` | `400`, **no** upstream connection |
| `Content-Length: 5` + `hello` | `400`, **no** upstream connection |
| static `/hello.txt` with `Content-Length: 5` | `400` |

`Content-Length: 0` failing is the tell — a zero-length body is not a disagreement, so a correct
guard would pass it.

Severity **high**: `Content-Length: 0` is emitted by most HTTP client libraries on POST/PUT/DELETE,
and many send it on GET too, so ordinary traffic is refused outright. No upstream request is even
attempted, which makes this total proxy unavailability for those clients rather than a degraded
path.

**Fix:** use `count()` before the subscript, or hold the lookups in locals:

```cpp
bool has_te=h.count("transfer-encoding"), has_cl=h.count("content-length");
if(h["content-length"].size()>1||h["transfer-encoding"].size()>1||(has_te&&has_cl)){fail(400);return;}
```

### SEC-006 — `Expect: 100-continue` is refused outright with 417

RFC 9110 §10.1.1 defines `Expect: 100-continue`: the client sends the head, waits for an interim
`100`, then sends the body. curl uses it automatically above a 1 KiB upload. This build answers
`417 Expectation Failed` before anything else — the whole request is refused.

The check is line 50:

```cpp
e(q<v.size()){size_t z=v.find(',',q);if(z==string::npos)z=v.size();if(trim(v.substr(q,z-q))=="close")close=true;q=z+1;}}if(h.count("expect")){fail(417);return;}if((ver=="HTTP/1.1"&&h["host"].size()!=1)||h["host"].size()>1){fail(400);return;}int si=c.ep->def;if
```

Measured (`evidence/ev_expect_1cfd33433d25__063b0d5e.log`): a client that sends the head and waits receives `417` and the body is
never transmitted; an "impatient" client that sends the body in the same write also gets `417`
with zero upstream connections, so the body is dropped either way. The control (`/api/x`, no
`Expect`) is `200` in the same log.

Severity **low**: no confidentiality or integrity loss, but every uploading client that uses the
standard option is refused, and a `417` is a hard failure rather than a retry-with-other-method.
Fix: answer `100 Continue` and keep the body-drain path, or strip `Expect` and forward.

### SEC-007 — standard chunked uploads (`Transfer-Encoding: chunked`) are refused with 400

`curl -T FILE`, `curl --data-binary @FILE` above 1 KiB, and every HTTP client that cannot know a
body length in advance switch to chunked transfer coding. This build refuses the framing header
outright, so that whole client class cannot reach the proxy at all — this is the second half of the framing gate whose first half already rejects any `Content-Length` (SEC-005), so no combination of the two framings survives.

The refusal is a single clause that fires on header presence alone, before any chunk parser would
run: line 55 (`fail(400)`): `if(!h["transfer-encoding"].empty()){fail(400);return;}`

```cpp
if(h["content-length"].size()>1||h["transfer-encoding"].size()>1||(h.count("transfer-encoding")&&!h["content-length"].empty())){fail(400);return;}
  ...
  if(!h["transfer-encoding"].empty()){fail(400);return;}
```

Even the degenerate form — `Transfer-Encoding: chunked` followed immediately by the terminating
`0\r\n\r\n` with zero payload — never reaches the upstream. Measured (`evidence/ev_te_063b0d5e.log`):

```
control  Content-Length: 5  -> 200, upstream receives 1 request with the 5-byte body
attack   Transfer-Encoding: chunked + "5\r\nhello\r\n0\r\n\r\n"  -> 400, upstream receives 0
attack   Transfer-Encoding: chunked + "0\r\n\r\n"                  -> 400, upstream receives 0
```

The upstream connection is never opened on the rejected path, so there is no proxy-side error page
and no partial forward — the request simply dies at the front door.

Severity is availability rather than memory safety: nothing is mis-parsed, but a standards-conforming
upload mode is unusable.

Because SEC-005 already makes *any* `Content-Length` fatal here, the two findings close over each
the other: there is no framing header — 0-length included — that this build will accept.


Contrast with the stage-05 kv builds, which do implement a chunk decoder and re-frame the request
upstream with a synthesised `Content-Length` (measured, `evidence/ev_te_kv_all.log`) — so the
defect is specific to this dialect, not inherent to the exercise.

### SEC-008 — a legal `Transfer-Encoding` + `Content-Length` pair from the upstream is rejected with 502

RFC 9112 §6.3 says a message may carry both framings: `Transfer-Encoding` wins and `Content-Length`
must be ignored. Real servers routinely emit the pair (any gzip/CDN layer in front of a chunked
response, and nginx does it by default when both `gzip` and proxy buffering interact). This build
treats the pair as a parse failure and answers 502 without relaying anything — the presence of both collections is the third clause of the response framing gate.

The reject is a single condition on presence of both collections: line 69 (`upstream_fail(c,502)`): `(!fields["content-length"].empty()&&!fields["transfer-encoding"].empty())`

```cpp
fields["transfer-encoding"].size()>1||(!fields["content-length"].empty()&&!fields["transfer-encoding"].empty())
```

Control and attack differ only by the extra `Content-Length` line, everything else identical
(`evidence/ev_rte_063b0d5e.log`):

```
upstream  HTTP/1.1 200 OK / Transfer-Encoding: chunked / Connection: close / "5\r\nhello\r\n0\r\n\r\n"
control   -> 200, body "hello"
attack    + Content-Length: 999                       -> 502, empty body
```

The value of the `Content-Length` is irrelevant — the clause fires on the header's presence, so even
a correct `Content-Length: 5` is rejected. Severity is availability: a legal, common upstream
response shape becomes a hard gateway error.

### SEC-009 — every status between `206` and `301` is relabelled `Service Unavailable`

`reason()` is a switch over the codes the server itself can emit, with a catch-all:

```cpp
static string reason(int n){switch(n){...case 206:return "Partial Content";case 301:return "Moved Permanently";...
case 502:return "Bad Gateway";default:return "Service Unavailable";}}
```

That set covers the static and error paths but not the ones only an upstream produces. On the proxy
route the status number is copied from the upstream verbatim, while the phrase is regenerated here,
so anything outside the table is relabelled. `204` lands on the catch-all and is emitted as
**`HTTP/1.1 204 Service Unavailable`** — a 2xx success carrying a 5xx phrase
(`evidence/ev_lifecycle_all.log`):

```
upstream 204 No Content          -> proxy "HTTP/1.1 204 Service Unavailable"
upstream 205 Reset Content       -> proxy "HTTP/1.1 205 Service Unavailable"
upstream 203 Non-Authoritative   -> proxy "HTTP/1.1 203 Service Unavailable"
upstream 304 Not Modified        -> proxy "HTTP/1.1 304 Not Modified"        (in the table)
upstream 599 Custom              -> proxy "HTTP/1.1 599 Service Unavailable" (correct by luck)
```

`204` is the one that matters in practice: it is the normal answer to a successful `DELETE`, `PUT`
with no payload, and many form/batch endpoints, and every one of them is described to the client as
a service failure. Logs, dashboards and any phrase-matching middleware inherit the wrong label. The
status digit itself is preserved, so clients that trust the number still work — this is corruption of
the phrase, not of the outcome.

Same family as the existing `206`/`416` finding (SEC-003) but a different surface: SEC-003 is a
locally-generated status losing its phrase, this is a *relayed* status losing it because the table
stops at `206`.

### SEC-010 — `SIGTERM` is ignored, so the server never shuts down while idle

`OPERATIONS.md:88-89` requires SIGTERM to stop new accepts within 250 ms, finish in-flight responses up to the configured drain deadline and exit within that deadline plus 500 ms; `CONFIGURATION.md:131` defines `toksec_drain_timeout` (default `5s`) as that deadline.

This build installs the master handler but blocks on an unbounded `waitpid`:

```cpp
while(!stopping){int status;pid_t p=waitpid(-1,&status,0);if(p>0){children.erase(p);if(!stopping)spawn();}else if(errno!=EINTR)break;}
```

`signal()` is used rather than `sigaction()` without `SA_RESTART` cleared, so the blocking
`waitpid(-1,&status,0)` is restarted every time the handler runs. Nothing wakes the master unless a
child changes state, and idle workers never do, so `stopping` is set and simply never observed:

```
workers=1 : 10.6 s after SIGTERM — master alive, CPU 0, workers alive, requests still 200
workers=2 : 10.6 s after SIGTERM — identical
```

The reverse of the sibling failure: the drain itself is correct (an in-flight proxied response
delivered all 10 bytes in 1.70 s and was not truncated), but the process tree then outlives its own
work. A supervisor that escalates to `SIGKILL` after its timeout kills a still-serving tree; one
that waits for exit hangs. `toksec_drain_timeout` is accepted and ignored — text search finds no
reference to it in the source at all.

### SEC-015 — the upstream chunk-size parser accepts digits-only sizes, so `0x5`, an 18-digit size and a leading space all yield an empty unterminated body

The upstream decoder validates the whole chunk-size field as hex before using it:

```cpp
string v=c.uraw.substr(0,e);auto semi=v.find(';');if(semi!=string::npos)v.resize(semi);
if(v.empty()||v.size()>16){upstream_fail(c,502);return false;}
unsigned long long n=0;for(char ch:v){int x;if(!hexval(ch,x)||n>(ULLONG_MAX>>4)){upstream_fail(c,502);return false;}n=n*16+x;}
```

`v.size()>16` hard-caps the field at **16 characters**, while a full `unsigned long long` needs 16
hex digits plus a possible leading zero — and the RFC does not restrict the width at all. Combined
with `hexval()` accepting only `[0-9a-fA-F]`, four ordinary forms fail *before* the size is ever
formed. The failure is not a 502, though: by the time the decoder runs, the response head has
already been committed with `Transfer-Encoding: chunked`, so the client gets a 200 whose body never
starts and never terminates:

```
upstream: 200 + TE: chunked, then "0x5\r\nhello\r\n0\r\n\r\n"
proxy   : "HTTP/1.1 200 OK / Transfer-Encoding: chunked / Connection: close / <nothing>"
```

All four affected forms, and the read-back through `http.client`:

```
0x5 hex prefix   -> 200 TE chunked, empty, unterminated -> IncompleteRead(0 bytes read)
leading space    -> 200 TE chunked, empty, unterminated
18 hex digits    -> 200 TE chunked, empty, unterminated -> IncompleteRead(0 bytes read)
negative -5      -> 200 TE chunked, empty, unterminated
legal "5;a=b"    -> 200, body "hello"      (control passes)
```

The severity comes from the client-side effect rather than the rarity: `IncompleteRead` is an
exception, not a short body, so a caching proxy or client that treats a truncated response as
success sees corruption, and one that treats it as an error retries a request that will keep
failing. `0x5` is the notable case — it is what several hand-written upstreams emit when they format
sizes in C — but the 18-digit form is reachable from any legitimate large object, since 16 hex digits
already exceeds this cap at 2^64 and any leading zero does too.

**Unique to this build.** The four siblings normalise all three forms to a clean 200 `hello`; only
this one has the 16-character cap plus strict-digit-only `hexval`. Files with a trailing `;` extension
are handled correctly (`semi` truncation), so this is the length/character class alone.
(`evidence/ev_chunkdef_all.log`)

## Artifact index

Standard stage-10 set: `target.cpp`, `target`, `target-san`, `nginx.conf`, `nginx_proxy.conf`, `probe_*.py`, `upstream*.py`, `evidence/*.log`.
- `evidence/truncation_trailing_bytes.txt` — trailing-byte truncation thresholds: body length for 0/1024/4090/4096/8192/16384/32768/65536 bytes after the header terminator.
- `evidence/ev_space_063b0d5e.log` — Space-only split: upstream head and returned `uid`
- `evidence/ev_bare_063b0d5e.log` — Bare `proxy_pass`, no URI: upstream head and returned `uid`
- `evidence/ev_cl_063b0d5e.log` — Content-Length matrix: no-CL control 200 with upstream, `CL: 0`, `CL: 5`+body and static+CL all 400 with no upstream connection
- `evidence/ev_expect_1cfd33433d25__063b0d5e.log` — `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control
- `evidence/ev_te_063b0d5e.log` — Control vs chunked upload: 200+forwarded body vs 400 with no upstream connection
- `evidence/ev_rte_063b0d5e.log` — Upstream response framing matrix: control, TE+CL pair, coding list, duplicate TE, bad chunk size
- `evidence/ev_nobody_063b0d5e.log` — Relayed-status phrase matrix: 204/205/203 all arrive as "Service Unavailable", 304 does not
- `evidence/ev_lifecycle_all.log` — Lifecycle matrix: SIGTERM/HUP behaviour, drain timing, worker replacement, orphan residue, restart attempt
- `evidence/ev_drain_false.log` — Directive acceptance: unknown http{} directives silently accepted by four builds; drain value never referenced
- `evidence/ev_chunkdef_all.log` — Chunk-size forms per build plus `http.client` read-back: 0x5/18-digit/space/-5 empty and unterminated here, clean on four siblings
