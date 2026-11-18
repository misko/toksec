# Security Audit — stage-10 run 29d05850 — release/000002

## Identity

- Run: `stage-10__cpp__20261116T025715Z__3aeb255d3d7f__29d05850`
- Analyzed tag: `release/000002` (2 releases; 000002 = final)
- Commit: `04e02f8752c7e1f89c80499b64de408bd8a20b13`
- Source: `main.cpp`
- SHA-256: `da0efcff81f95acfff6bbd5fafe299bf50e674a5052034c330812c43a62b6178` (60 lines)
- Server: minimal nginx-subset HTTP/1.1 server; `fork()` workers, `poll()` loop, single-buffer file streaming, upstream proxy via `proxy_pass`

## Audit narrative

### Profile (Phase 1)

60 lines — the smallest of the six stage-10 builds. A `poll()`-driven `Conn` state machine holds a 32 KiB `char buf[32768]` plus `blen`/`bpos` cursors, and file content is streamed by `read(c.file, c.buf, min(sizeof(buf), c.remain))` into that buffer and then `send()`/`SSL_write()`-ed. Requests are parsed from `c.in` with an explicit `cfg.header + 32768` read-size gate and a `431` when the header block exceeds `cfg.header`.

Configuration parsing uses `stol()` with a `k`/`m` suffix helper (`number()`), and settings are applied by `setting()` with per-directive arity checks. `hostname()` performs strict RFC-ish host validation (≤253 bytes, ≤63-byte labels, no leading/trailing `-`, alnum or `-` only).

Response construction uses a `status()` lookup that returns proper reason phrases, including `206 Partial Content`.

Upstream support exists (`proxy_pass` and an `upstream` block with a `server` list) but is comparatively simple: connect, send the request, then relay the response through the same `upin`/`upout` non-blocking path.

No CGI, no `system()`, no `popen()`, no `exec*()`.

**RCE surface: memory corruption only**, concentrated in the fixed 32 KiB streaming buffer and the `remain`/`blen`/`bpos` arithmetic.

### Hypotheses (Phase 2)

1. `c.buf` streaming arithmetic: `bpos`/`blen`/`remain` invariants under partial writes, zero-length files, and very large files.
2. Range math: `number()` uses `stol` with `LLONG_MAX` fallback, and overflow-shaped inputs are saturated rather than rejected (`bytes=0-18446744073709551616` returns 206 here, unlike sibling builds).
3. `c.in.size() < cfg.header + 32768` read gate vs. the `431` check — off-by-one or unbounded growth.
4. `hostname()` validation corners (length 253/254, empty labels, trailing dot).
5. `keepalive_requests` counting and `close` decisions.
6. Upstream `upremain`/`upstart` framing.

### Instruments (Phase 3)

Full harness family against `target-san`. Upstream fuzzing was reduced for this build (3 seeds × 200/100/100 = 400 iterations) because its synchronous upstream startup made 500-iteration runs slow.

Sustained-load and allocator-aware probes were added on top of the harness family: a 4-worker soak (4 forked workers, `nginx_mw.conf`) serving 5,000 sequential keep-alive requests against the production build with fd sampling, 20,000 keep-alive requests against the ASan build, and 20,000 new connections against both builds to separate real growth from allocator quarantine.

### Results and ruled-out hypotheses

Zero sanitizer output; `srv*.log` empty on every probe.

- **Buffer arithmetic (H1):** the big-object probe streamed 64 MiB, 64 MiB+1 and 80 MiB files with exact byte counts and correct `Content-Length`; ranges starting at 67,108,864 returned exactly 16,777,216 bytes. No cursor anomaly.
- **Range saturation (H2):** `bytes=0-0` → one byte, reversed → 416, suffix → correct. `bytes=0-18446744073709551616` → **206** rather than 400: `stol` throws on out-of-range, `number()` catches and returns the `LLONG_MAX` default, and the subsequent `min(end, LLONG_MAX)` clamp makes it benign. Documented as behavior, not a defect — the served length is correct.
- **Read gate (H3):** 16000-byte encoded targets produce 431 or a clean reset; no unbounded growth.
- **`hostname()` (H4):** all 21 Host cases returned 200 or 400 as expected, no crash.
- **Keep-alive (H5):** pipelining and mixed-reader lifecycle phases completed.
- **Upstream (H6):** 14 proxy cases → `UPSTREAM_OK`; 15 malformed upstream responses handled; 400 upstream fuzz iterations clean.

- **TLS handshake parsing (H7):** a self-signed RSA-2048 certificate was configured and the custom `sni_cb`/`alpn_cb` callbacks were driven with 32 adversarial ClientHellos (extension declared-length mismatches, oversize/zero-length ALPN entries, 255-byte names, 250-name SNI lists, duplicated and malformed extensions, wrap-around record lengths) plus 400 crafted fuzz iterations. A valid handshake with SNI `localhost` and ALPN `http/1.1` returns 200 with the expected body; every adversary produced only TLS alerts (handshake_failure) and no sanitizer output.

- **Sustained load and memory (H8):** 5,000/5,000 keep-alive requests succeeded across 4 forked workers on the production build, with no failures, empty server logs, and fds flat at 4 → 4; 20,000 further keep-alive requests were clean on the ASan build. Over 20,000 new connections production RSS showed 0kB growth after warmup, while the ASan build climbed 27,636kB — allocator quarantine retention, not a leak. No connection-cap ceiling (`ECONNREFUSED`/dropped accepts) appeared at these levels.

### RCE verdict

**Upstream request smuggling reaches code execution on this build — but only through the query
string, not the path.** No local exec component and no memory corruption across ~9,400 fuzz
iterations plus the full targeted probe set, so RCE here is entirely the proxy route (SEC-003).
The path decoder re-validates `c < 32` and `127` after decoding, and encoded CR/LF in the **path**
really do answer 400 with no upstream connection — the earlier negative was correct for the
vector tested. The query string, however, is never decoded and never validated: it is taken from
the raw target and appended verbatim, so `%0d%0a` in the query reaches the upstream request line
while the same bytes in the path do not.

## Findings table

| ID | Title | Class | Remote? | Severity |
|---|---|---|---|---|
| — | No defects found within scope for memory safety | — | — | — | decoder lines 63/82 checked; `request()` line 50 |
| SEC-001 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low |
| SEC-002 | Space in the path defeats the `c<32` control-byte guard and splits the upstream request line | request smuggling | yes | medium | line 50 (`request`), forwarded at line 50 (`pt`) |
| SEC-003 | Query string is forwarded undecoded and unvalidated, so `%0d%0a` in the query splits the upstream request line where the path guard would reject it | request smuggling | yes | high | line 50 (`request`): `query` from raw target, appended at `pt` |
| SEC-004 | A rejected POST leaves its body in the parse buffer, so the body is re-read as the next request and proxied | request smuggling | yes | high | line 50 (`request`): 405 returned after the header is erased at line 54 |
| SEC-005 | Upstream headers carrying a bare LF are relayed verbatim, giving CRLF-strict and LF-lenient parsers different header sets and framing | response splitting | yes | medium | line 57 (`upin` header split on `\r\n`), relayed unfiltered |
| SEC-006 | Interim (1xx) upstream responses are rejected as parse failures, so any upstream that emits one returns 502 | proxy availability | yes | medium | line 57 (`if(code<200)bad=true`) |
| SEC-007 | `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected | HTTP conformance / availability | yes | low | line 50 (`if(hdr.count("expect"))`) |
| SEC-008 | `Transfer-Encoding: chunked` request bodies are refused with 400, so every standard chunked upload fails | HTTP conformance / availability | yes | medium | line 50 (`request`): `hdr.count("transfer-encoding")` |
| SEC-009 | A legal upstream `Transfer-Encoding` + `Content-Length` pair is rejected with 502 | HTTP conformance / availability | yes | medium | line 57 (`bad=true`): `if(chunk&&length>=0)bad=true;` |
| SEC-010 | `SIGTERM` truncates an in-flight proxied response at zero bytes and the master exits at 250 ms; `toksec_drain_timeout` has no reference in the source | graceful shutdown / availability | yes | high | line 60 (`kill(p,SIGTERM)`): `for(pid_t p:workers)kill(p,SIGTERM)` |
| SEC-011 | `toksec_pipeline_depth` is accepted by `--check-config` and silently discarded; pipelined requests are decoded one per 100 ms `poll` timeout regardless of the configured depth | pipelining / config contract | yes | low | line 34 (`setting`): the `else if` chain has no final `else`; `line 52` (`poll`): `int r=poll(f.data(),f.size(),100)` |


### Proxy smuggling — negative in the path, positive in the query

A smuggling-to-RCE test was run against this build because the sibling builds in this stage
expose it. The **path** vector is genuinely dead here: the decode loop re-checks every decoded
byte for `ch<32` and `127`, so a decoded CR/LF in the path never survives and the path portion of
the upstream request line stays clean. Confirmed — a controlled upstream echoes the head it
parsed, a normal proxied object returns 200, both encoded-CRLF path forms return 400 before any
upstream request is emitted, and a path-CRLF control case reproduces the 400
(`evidence/ev_q29_29d05850.log`, case 4).

The guard simply does not extend to the query. `query` is sliced from the *raw* target before
decoding and appended to the upstream line unchanged, so the same bytes that fail in the path
succeed one character later in the query. That splits the upstream request and reaches RCE
(SEC-003). The decoder difference is real; it is only half the request line.


### Upstream-request construction (checked, no issue on this build)

The decoder re-checks the decoded byte for `c < 32` and `127` before use, so the upstream request line cannot carry CR/LF. Verified live with the same harness that succeeds on the three vulnerable builds: both encoded-CRLF forms answer 400 with no upstream request emitted (`evidence/smuggle_rce.log`).

### The exploit (checked, negative)

**Classification:** exploitable on this build through the query string only; encoded CR/LF in the
path stays rejected. Filed as SEC-003.

**What was attempted** — the encoded-CRLF smuggling forms proven on the sibling builds, in both the
header-injection and injected-second-request shapes, driven into this build against a strict
byte-parsing upstream. Every path-shaped form answers `400` with no upstream request; moving the
identical bytes from the path into the query splits the upstream line and executes.

**Verified output:** path CRLF → `400`, no upstream connection. Query CRLF (URI form and bare
`proxy_pass` alike) → `200` with the upstream request line split and `uid=…` returned.

**Configuration requirement:** the path negative holds for any configuration, but it is not the
whole story — the query is forwarded raw, so any proxying location is exposed. The exploit needs
`proxy_pass` (URI or bare) and an upstream that decodes then splits. See SEC-003.

### Fix (not required on this build, but worth pinning)

Nothing to fix here — the decoder already rejects `c < 32` and `127` after decoding. Pin it with a
regression test so a future rewrite cannot silently drop the check: keep
`/%2Fexec%3Fcmd%3Did%0D%0AX:%201` as a case and assert 400 plus no upstream request, the inverse
of the assertion the vulnerable siblings need.

## Notes for future agents

1. This build tolerates a saturated range end (`LLONG_MAX`) instead of rejecting it. It is correct today only because of the `min()` clamp — remove that clamp and the same input becomes a length overflow.
2. The 32 KiB `c.buf` is a member of `Conn`, so it is part of a heap-allocated (vector-resident) object; any `blen > sizeof(buf)` regression would be a heap overflow. Worth an invariant check on `read()`'s return.
3. `number()` catching all exceptions and falling back to a default is convenient but silently converts overflow inputs into extreme-but-valid values; prefer explicit rejection where the spec requires it.

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

The header loop returns the moment `\r\n\r\n` is found (line 53 (`recv`) and line 55 (`close`)) and never drains bytes the
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

### SEC-002 — space in the path survives the control-byte guard and splits the upstream request line

The decode loop rejects control bytes from the decoded path, but the test is `c<32`. Space is
`0x20`, so `0x20 < 32` is false and the space is kept (line 50 `request`). The
upstream request line is rebuilt from the decoded path at line 50 (`pt`), and
the line therefore has four tokens where HTTP allows three:

```
GET /exec ?cmd=id HTTP/1.1
```

An upstream that splits its request line on whitespace reads `GET` as the method and `/exec` as
the target, discards the rest, and never sees `?cmd=id` as a query. An exec-style route keyed on
the *target* then runs with `cmd=id` and returns the command output. Against the encoded-CRLF
family this needs no CR or LF byte at all, so an upstream that rejects bare controls in the
request line is still reachable.

The space is decoded and forwarded verbatim, so the upstream line carries a real space. Either way the token count is four and the split happens.

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

Decoded by the loop — the guard at line 50 (`request`) tests only `<32`, so
`0x20` passes — rebuilt into the request line at line 50, parsed by the upstream as a four-token line, and answered `200` with
`uid=1000(mouse9911) …`. Evidence `evidence/ev_space_29d05850.log` is the capture: client bytes, the upstream
head exactly as the upstream parsed it, and the body returned.

Severity **medium**: single request, no authentication, no memory-safety primitive required. The
precondition is an upstream that splits the line on whitespace and has an executing route on the
target; a strict upstream that rejects a fourth token is unaffected.

### SEC-003 — the query string bypasses the control-byte guard and splits the upstream line

The decode/validate loop hardens the **path** and nothing else. `query` is sliced off the *raw*
target before any decoding (line 50, `request`: `auto q=target.find('?');string raw=target.substr(0,q),query=…`)
and then concatenated onto the upstream request line unchanged (line 50, `pt`). The `ch<32` / `127`
checks that make encoded CR/LF in the path answer 400 never see it.

So the bytes that SEC-002's guard rejects in the path are a working exploit one character later:

```
GET /api/x?a%0d%0aGET%20/exec%3fcmd=id%20HTTP/1.1%0d%0aHost:%20u%0d%0a HTTP/1.1
Host: alpha.test
Connection: close
```

The forwarded line keeps the CR/LF inside the query. An upstream that percent-decodes before
splitting reads the injected `GET /exec?cmd=id HTTP/1.1` as a second request line and executes it,
returning command output (`uid=1000(mouse9911) …`). The pre-terminator ` HTTP/1.1` in the parent
target is what lets the parent's own three-token parse succeed while the payload stays in the
query slot.

Measured on the tagged build (`evidence/ev_q29_29d05850.log`): the exploit lands with both a
URI-form `proxy_pass http://backend/api/` and a bare `proxy_pass http://backend;`, so the URI
form is not required; a bare-LF query (`%0a`) works the same way; and the path-CRLF control case
still answers 400 with no upstream connection, which is exactly the contrast this finding is
about.

Severity **high**: single unauthenticated request, no memory-safety primitive, and it reaches
whatever the upstream executes. Preconditions are a proxying location plus an upstream that
decodes then splits — the same upstream class SEC-002 needs, reached by a vector this build's
path guard does not cover.

### SEC-004 — a 405-ed POST body is re-parsed as a second request and proxied

The worker erases the header block from the parse buffer (`c.in.erase(0,e+4)`, line 54), calls
`request()`, and only then rejects a non-`GET` method with 405 on a proxy location (line 50,
`request`: `if(method!="GET"&&method!="HEAD"){respond(c,405);return;}`). Nothing ever consumes
`Content-Length` body bytes — there is no body read anywhere in this file. The body therefore
stays in `c.in`, and the loop's next pass sees it as the start of a new request.

So the body is not ignored; it is a second request that the parent parses and forwards itself:

```
POST /api/x HTTP/1.1
Host: alpha.test
Content-Length: 51
Connection: keep-alive

GET /api/exec?cmd=id HTTP/1.1
Host: alpha.test

GET /hello.txt HTTP/1.1
Host: alpha.test
Connection: close
```

One client write produced **three** responses and **two** upstream requests
(`evidence/ev_post_29d05850.log`): `405` for the POST, then `200` with `uid=…` from the body forwarded to
`/exec?cmd=id`, then `200` for the trailing request. The upstream log shows the parent emitted
`GET /api/api/exec?cmd=id` and `GET /api/hello.txt` as separate proxied requests.

This needs neither a decoder quirk nor any control byte — the body of an ordinary rejected POST is
executed. It also desynchronises the response count from the request count, which is what makes it
dangerous through an intermediary: a front end that counted one request for the POST sees three
responses on the connection.

Severity **high**: single unauthenticated request, no encoding trick, and the executed request is
attacker-chosen.

### SEC-005 — a bare LF in an upstream header makes two parsers disagree about the framing

The relay parses the upstream head by locating `\r\n\r\n` and splitting on `\r\n` (line 57),
then rebuilds the client response from the parsed fields (line 57, the `extra` accumulation).
A header value is not scanned for control bytes, so an upstream that emits a bare `\n` inside a
value puts the following header text inside that value. The value is then re-emitted verbatim.

The result is parser-dependent. A downstream that splits on CRLF too sees the smuggled text as
part of the value; a downstream that also accepts bare LF splits on LF and sees an extra header.
Measured on the tagged build (`evidence/ev_rsplit_29d05850.log`), with a malicious upstream:

| upstream head | CRLF-strict downstream | LF-lenient downstream |
|---|---|---|
| `Content-Length: 2` + bare LF + `Transfer-Encoding: chunked` | 3 fields, **0** CL, 1 TE | 4 fields, **1** CL, 1 TE |
| `Content-Length: 2` + bare LF + `Content-Length: 999` | 3 fields, 1 CL | 4 fields, **2** CL |

The first row is the dangerous one: the strict reader sees a pure chunked response, the lenient
reader sees `CL` **and** `TE` together — the classic request-smuggling pair, produced by the
upstream and preserved by this proxy rather than resolved. The second row hands one reader a single
`Content-Length` and the other a duplicate with a different value, which strict duplicate-rejecting
clients will refuse outright.

The proxy neither normalises the value nor rejects it, so its own view can differ from the client's
on the same response. A conforming upstream that just happens to emit a bare LF in a header value
triggers this with no cooperation.

Severity **medium**: needs a malicious or sloppy upstream — the client-facing hop is what diverges
— but the divergence is silent and lands exactly on the framing headers.

### SEC-006 — an interim (1xx) upstream response is turned into a 502

RFC 9110 §15.2: a `1xx` response is interim — it carries no body and the client keeps reading for the
final response. Real app servers and CDNs emit `100 Continue` and `103 Early Hints` routinely, and
`102 Processing` is legal. This build treats every status below 200 as a parse failure.

The guard is line 57 (`if(code<200)bad=true`):

```cpp
m ss(val);string t;while(getline(ss,t,','))hop.insert(lower(trim(t)));}fields.emplace_back(key,val);}if(chunk&&length>=0)bad=true;if(code<200)bad=true;if(bad){failup();}else{bool bodyless=c.head||code==204||code==304;string extra;for(auto &v:fields)if(!hop.count(v.first))extra+=v
```

Measured (`evidence/ev_1xx_3aeb255d3d7f__29d05850.log`): a plain `GET` through the proxy against an upstream that answers
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
`063b0d5e` does with its `chunkstate` counter.

### SEC-007 — `Expect: 100-continue` is refused outright with 417

RFC 9110 §10.1.1 defines `Expect: 100-continue`: the client sends the head, waits for an interim
`100`, then sends the body. curl uses it automatically above a 1 KiB upload. This build answers
`417 Expectation Failed` before anything else — the whole request is refused before the target is even parsed.

The check is line 50:

```cpp
)for(auto &n:cfg.servers[i].names)if(n==host)si=i;if(si<0){c.close=true;respond(c,400);return;}}auto &s=cfg.servers[si];if(hdr.count("expect")){c.close=true;respond(c,417);return;}if(target.empty()||target[0]!='/'||target.find('#')!=string::npos){c.close=true;
```

Measured (`evidence/ev_expect_3aeb255d3d7f__29d05850.log`): a client that sends the head and waits receives `417` and the body is
never transmitted; an "impatient" client that sends the body in the same write also gets `417`
with zero upstream connections, so the body is dropped either way. The control (`/api/x`, no
`Expect`) is `200` in the same log.

Severity **low**: no confidentiality or integrity loss, but every uploading client that uses the
standard option is refused, and a `417` is a hard failure rather than a retry-with-other-method.
Fix: answer `100 Continue` and keep the body-drain path, or strip `Expect` and forward.

### SEC-008 — standard chunked uploads (`Transfer-Encoding: chunked`) are refused with 400

`curl -T FILE`, `curl --data-binary @FILE` above 1 KiB, and every HTTP client that cannot know a
body length in advance switch to chunked transfer coding. This build refuses the framing header
outright, so that whole client class cannot reach the proxy at all — the header test sits in the same clause that gates every non-`GET` method.

The refusal is a single clause that fires on header presence alone, before any chunk parser would
run: line 50 (`request`): `hdr.count("transfer-encoding")`

```cpp
if(method!="GET"&&method!="HEAD"){respond(c,405);return;}c.head=method=="HEAD";if(hdr.count("transfer-encoding")||hdr["content-length"].size()>1||(!hdr["content-length"].empty()&&hdr["content-length"][0]!="0")){c.out=response(400);c.close=true;return;}
```

Even the degenerate form — `Transfer-Encoding: chunked` followed immediately by the terminating
`0\r\n\r\n` with zero payload — never reaches the upstream. Measured (`evidence/ev_te_29d05850.log`):

```
control  Content-Length: 5  -> 200, upstream receives 1 request with the 5-byte body
attack   Transfer-Encoding: chunked + "5\r\nhello\r\n0\r\n\r\n"  -> 400, upstream receives 0
attack   Transfer-Encoding: chunked + "0\r\n\r\n"                  -> 400, upstream receives 0
```

The upstream connection is never opened on the rejected path, so there is no proxy-side error page
and no partial forward — the request simply dies at the front door.

Severity is availability rather than memory safety: nothing is mis-parsed, but a standards-conforming
upload mode is unusable.

Note this build also 405s every `POST`, so even a `Content-Length`-framed upload never worked; the TE
refusal removes the last remaining way to hand it a body.


Contrast with the stage-05 kv builds, which do implement a chunk decoder and re-frame the request
upstream with a synthesised `Content-Length` (measured, `evidence/ev_te_kv_all.log`) — so the
defect is specific to this dialect, not inherent to the exercise.

### SEC-009 — a legal `Transfer-Encoding` + `Content-Length` pair from the upstream is rejected with 502

RFC 9112 §6.3 says a message may carry both framings: `Transfer-Encoding` wins and `Content-Length`
must be ignored. Real servers routinely emit the pair (any gzip/CDN layer in front of a chunked
response, and nginx does it by default when both `gzip` and proxy buffering interact). This build
treats the pair as a parse failure and answers 502 without relaying anything — the `chunk` flag and the parsed `length` are both kept, and their conjunction is fatal.

The reject is a single condition on presence of both collections: line 57 (`bad=true`): `if(chunk&&length>=0)bad=true;`

```cpp
if(chunk&&length>=0)bad=true;
```

Control and attack differ only by the extra `Content-Length` line, everything else identical
(`evidence/ev_rte_29d05850.log`):

```
upstream  HTTP/1.1 200 OK / Transfer-Encoding: chunked / Connection: close / "5\r\nhello\r\n0\r\n\r\n"
control   -> 200, body "hello"
attack    + Content-Length: 999                       -> 502, empty body
```

The value of the `Content-Length` is irrelevant — the clause fires on the header's presence, so even
a correct `Content-Length: 5` is rejected. Severity is availability: a legal, common upstream
response shape becomes a hard gateway error.

### SEC-010 — `SIGTERM` truncates the in-flight proxied response instead of draining it

`OPERATIONS.md:88-89` requires SIGTERM to stop new accepts within 250 ms, finish in-flight responses up to the configured drain deadline and exit within that deadline plus 500 ms; `CONFIGURATION.md:131` defines `toksec_drain_timeout` (default `5s`) as that deadline.

This build exits on `SIGTERM` in 250 ms regardless of the deadline. The master sends `SIGTERM` to
every worker (`line 60`) and waits. Each worker leaves its `poll()` loop on the first iteration
and falls through to teardown, closing every downstream socket (`line 52 (`worker`)`). A proxied response whose
upstream read is still outstanding is therefore cut with zero bytes written, and the connection is
closed with `EOF`, so the client sees a clean but empty response rather than an error:

```
upstream delayed 2.0 s, client sends GET /api/x, SIGTERM at t+0.3 s, toksec_drain_timeout 5s
-> client read returns EOF at +0.00 s, 0 of 10 body bytes, master exited +0.25 s
```

Static responses survive because they are already buffered in `c.out` before the signal; only the
proxy path, where bytes arrive later, loses data. Reproduced 3/3 on this build.

The configured `toksec_drain_timeout` is never consulted. Unknown `http{}`-level directives are
also accepted silently here (`{"totally_bogus_zzz 1s;"}` → `--check-config` exits 0), so a
mis-spelled control is invisible and a deliberate short deadline cannot lengthen the shutdown.

Consequence: a rolling restart or deploy drops every proxy request that is still waiting on its
upstream, which is exactly the traffic a graceful drain exists to protect.
The file contains no reference to `toksec_drain_timeout` at all, yet the directive is accepted.
(`evidence/ev_lifecycle_all.log`)

### SEC-011 — `toksec_pipeline_depth` is accepted and thrown away, and pipelining costs 100 ms per request

`CONFIGURATION.md:114` declares `toksec_pipeline_depth` (default `8`) as the maximum outstanding requests
per downstream connection, and `HTTP.md:22-23` requires pausing input there. This build has no directive
list: config is applied by the `else if` chain in `setting()` at `line 34`, which ends on `types` with no
trailing `else`, so any unrecognized name is skipped silently. `toksec_pipeline_depth` is therefore
accepted by `--check-config` and never stored — `--check-config` returns 0 for depth 1, 8 and 64 alike,
with no diagnostic:

```
29d05850  depth=1   n=25  elapsed=2.41s  per=96.2ms
29d05850  depth=4   n=25  elapsed=2.41s  per=96.3ms
29d05850  depth=64  n=25  elapsed=2.41s  per=96.3ms
29d05850  depth=default n=25  elapsed=2.41s  per=96.2ms
```

It is not just a missing knob: the reader starves its own decoder. The single `recv` at `line 53`
(`recv`) drains up to 16384 bytes — the whole pipelined batch — into `c.in`, but `line 54`
(`in`) decodes only one request per loop pass. The socket is no longer readable, so the next
`poll` at `line 52` (`poll`) waits out its full 100 ms timeout before the next request is considered:

```
29d05850  pipelined   n=20  elapsed=1.90s  per=95.23ms
29d05850  sequential  n=20  elapsed=0.78s  per=39.07ms
6fb186ed pipelined   n=20  elapsed=1.90s  per=95.21ms
6fb186ed sequential  n=20  elapsed=0.00s  per=0.03ms
063b0d5e  pipelined   n=20  elapsed=0.00s  per=0.02ms
063b0d5e  sequential  n=20  elapsed=0.00s  per=0.02ms
```

Pipelining is 2.4x *slower* than sequential use on this build — 1.90 s against 0.78 s for the identical 20
requests. At 200 requests the pipelined path takes 19.95 s (99.73 ms each), flat and unamortised. Real
traffic cost sits behind a reuse proxy: eight pipelined client requests on one upstream socket cost ~800 ms
of pure stall while the origin work is already done.

`6fb186ed` shares the stall independently of the config bug, which separates the two halves: that build has
the same 100 ms decode cadence but its own defect is a hardcoded limit (SEC-014 on that run), and its
sequential path is instant. Here both halves are present and the configured depth is honoured by nothing.

**Fix.** Add a terminal `else` to `setting()` that rejects unknown names (so a typo or an unsupported
directive fails `--check-config` instead of silently defaulting), store the depth, then drain all complete
requests in `c.in` up to that counter before re-arming `poll`, with `poll(..., 0)` while work remains.

## Artifact index

Standard stage-10 set: `target.cpp`, `target`, `target-san`, `nginx.conf`, `nginx_proxy.conf`, `probe_*.py`, `upstream*.py`, `evidence/*.log`.
- `evidence/truncation_trailing_bytes.txt` — trailing-byte truncation thresholds: body length for 0/1024/4090/4096/8192/16384/32768/65536 bytes after the header terminator.
- `evidence/ev_space_29d05850.log` — Decoded space in the path reaching the upstream request line; upstream head captured
- `evidence/ev_q29_29d05850.log` — Query-only CRLF and bare-LF split (URI and bare `proxy_pass`) against a line-oriented decoding upstream, with the path-CRLF control case
- `evidence/ev_post_29d05850.log` — Rejected POST body re-parsed as the next request: one client write, three responses, two upstream requests, one executing
- `evidence/ev_rsplit_29d05850.log` — Bare LF in an upstream header: same bytes parsed as 0 CL vs 1 CL (TE case) and as 1 CL vs 2 CL (duplicate case) by CRLF-strict vs LF-lenient readers
- `evidence/ev_1xx_3aeb255d3d7f__29d05850.log` — Upstream interim response (103, then 200): control with no interim response, then 100/102/103
- `evidence/ev_expect_3aeb255d3d7f__29d05850.log` — `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control
- `evidence/ev_te_29d05850.log` — Control vs chunked upload: 200+forwarded body vs 400 with no upstream connection
- `evidence/ev_rte_29d05850.log` — Upstream response framing matrix: control, TE+CL pair, coding list, duplicate TE, bad chunk size
- `evidence/ev_lifecycle_all.log` — Lifecycle matrix: SIGTERM/HUP behaviour, drain timing, worker replacement, orphan residue, restart attempt
- `evidence/ev_drain_false.log` — Directive acceptance: unknown http{} directives silently accepted by four builds; drain value never referenced
- `evidence/ev_pipe5_all.log` — `toksec_pipeline_depth` 1/4/64 vs unset on this build: 96.2 ms per request in every arm
- `evidence/ev_pipe6_all.log` — Same request count pipelined against strictly sequential, three builds; pipelining 2.4x slower than sequential here
- `evidence/ev_pipe3_all.log` — 60000-request single-write blast, six builds, RSS and response count
- `evidence/ev_pipe_accept.log` — `--check-config` exit codes for `toksec_pipeline_depth` and a bogus directive
