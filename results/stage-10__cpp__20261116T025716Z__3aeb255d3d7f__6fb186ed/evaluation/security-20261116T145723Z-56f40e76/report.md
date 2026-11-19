# Security Audit — stage-10 run 6fb186ed — release/000004

## Identity

- Run: `stage-10__cpp__20261116T025716Z__3aeb255d3d7f__6fb186ed`
- Analyzed tag: `release/000004` (4 releases; 000004 = final)
- Commit: `ecfd36b6e9fed47e9f3656dce23f8abaa0e1f1bd`
- Source: `main.cpp`
- SHA-256: `a3c56a4b6e2e71c4739a6e696888c17ef8903faa98912dc4d73e6b506e757a35` (75 lines)
- Server: nginx-subset HTTP/1.1 server; `fork()` workers, `poll()` loop, own `safeopen()` resolver, upstream proxy with non-blocking upstream handling

## Audit narrative

### Profile (Phase 1)

75-line C++ nginx subset. Requests are parsed from a header string into a `map<string, vector<string>>` of headers. Files are resolved by a bespoke `safeopen(root, path)` that opens the root with `O_DIRECTORY|O_NOFOLLOW`, then walks each component with `openat(…, O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)`.

Two implementation details are specific to this build:

1. **`safeopen()` does not add `O_DIRECTORY` for intermediate components** (unlike run 2's `safeopen()` and run 1's per-component walk). Each component is opened read-only with `O_NOFOLLOW`, and `O_INCREMENTAL` directory-ness is not asserted. A regular file in an intermediate position therefore opens successfully and the following `openat()` fails with `ENOTDIR`. This is safe (returns 404/403) but differs from its siblings.
2. **`response()` has an incomplete reason-phrase table**: it covers 200/301/302/400/403/404/405/417/431 and falls back to `"Error"`. Consequently `206` is emitted as `HTTP/1.1 206 Error` and `416` as `HTTP/1.1 416 Error`. Status codes, `Content-Range` and `Content-Length` are all correct.

No CGI, no `system()`, no `popen()`, no `exec*()`.

**RCE surface: memory corruption only.**

### Hypotheses (Phase 2)

1. `safeopen()` without `O_DIRECTORY`: opening a regular file as an intermediate component, then `openat()` on it (which returns `ENOTDIR`, never a symlink escape).
2. Reason-phrase fallback path — cosmetic, but check that it is not used to build anything but the status line.
3. Range math and the 64 MiB cap: this build returns **403** for over-cap files (like run 3).
4. Upstream relay with non-blocking upstream fd and `upfd`/`upsend` framing.
5. Header/body/`Expect` handling, return-code paths, empty body handling.
6. 4 release iterations — this run had the most revision churn and thus the most configuration surface.

### Instruments (Phase 3)

Full harness family against `target-san`; upstream fuzzing reduced to 3 seeds × 500/200/500 = 1200 iterations for startup-time reasons.

Sustained-load and allocator-aware probes were added on top of the harness family: a 4-worker soak (4 forked workers, `nginx_mw.conf`) serving 5,000 sequential keep-alive requests against the production build with fd sampling, 20,000 keep-alive requests against the ASan build, and 20,000 new connections against both builds to separate real growth from allocator quarantine.

### Results and ruled-out hypotheses

Zero sanitizer output; `srv*.log` empty on every probe.

- **`safeopen()` (H1):** 21/21 path cases sane; traversal 403; trailing slash → 404 (differs from siblings' 403, consistent with the missing `O_DIRECTORY` semantics); no crash, no escape.
- **Reason fallback (H2):** `206 Error` / `416 Error` observed in `range_probe.log` and `big_object_probe.log`; body lengths and `Content-Range` correct. Cosmetic only.
- **Range/cap (H3):** `bytes=0-0` → one byte with 206; reversed → 416; suffix → correct; 20-digit overflow → 400; exactly 64 MiB served; 64 MiB+1 and 80 MiB → **403**; ranges anchored at 67,108,864 returned correct remainders despite the odd reason phrase.
- **Upstream (H4):** 14 proxy cases → `UPSTREAM_OK`; 15 malformed upstream responses handled; 1200 upstream fuzz iterations clean.
- **Headers/body (H5):** 47 header cases and 22 body cases all expected; POST → 405.
- **Churn (H6):** all lifecycle phases completed.

- **TLS handshake parsing (H7):** a self-signed RSA-2048 certificate was configured and the custom `sni_cb`/`alpn_cb` callbacks were driven with 32 adversarial ClientHellos (extension declared-length mismatches, oversize/zero-length ALPN entries, 255-byte names, 250-name SNI lists, duplicated and malformed extensions, wrap-around record lengths) plus 400 crafted fuzz iterations. A valid handshake with SNI `localhost` and ALPN `http/1.1` returns 200 with the expected body; every adversary produced only TLS alerts (handshake_failure) and no sanitizer output.

- **Sustained load and memory (H8):** 5,000/5,000 keep-alive requests succeeded across 4 forked workers on the production build, with no failures, empty server logs, and fds flat at 4 → 4; 20,000 further keep-alive requests were clean on the ASan build. Over 20,000 new connections production RSS showed 0kB growth after warmup, while the ASan build climbed 13,228kB — allocator quarantine retention, not a leak. No connection-cap ceiling (`ECONNREFUSED`/dropped accepts) appeared at these levels.

### RCE verdict

**RCE found — via the upstream.** No local code-execution component and no memory corruption across
~11,700 fuzz iterations, but the build is a reverse proxy whose decoder passes decoded CR/LF into
the upstream request line, so an exec-capable backend runs attacker input. Detail below.

## Findings table

| ID | Title | Class | Remote? | Severity | Source line |
|---|---|---|---|---|---|
| SEC-001 | CRLF survives percent-decoding into the upstream request line | request smuggling | Yes | medium | line 62 (`decodepath` decode loop) |
| SEC-002 | Smuggled request reaches a code-executing upstream route | RCE on upstream | Yes | high | line 62 → upstream request line |
| SEC-003 | `206` and `416` emitted with reason phrase `Error` | HTTP conformance / cosmetic | Yes | informational | line 60 (`response()` reason chain) |
| SEC-004 | Decoded CRLF reaches the directory-301 `Location` header, splitting the response | Response splitting | Yes | low | line 62 (`decodepath`) -> redirect `Location` at line 69 |
| SEC-005 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 74 (`recv`) |
| SEC-007 | Space in the path defeats the `c<32` guard and splits the upstream request line | request smuggling | yes | medium | line 62 (`decodepath`), forwarded at line 68 (`uri`) |
| SEC-008 | Split also works with a bare `proxy_pass`, no URI needed | request smuggling | yes | medium | rebuild at line 68 (`uri`), guard line 62 (`decodepath`) |
| SEC-009 | Upstream headers carrying a bare LF are relayed verbatim, giving CRLF-strict and LF-lenient parsers different header sets and framing | response splitting | yes | medium | upstream head split on `\r\n` and rebuilt field by field |
| SEC-010 | `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected | HTTP conformance / availability | yes | low | line 65 (`if(headers.count("expect"))`) |
| SEC-011 | `Transfer-Encoding: chunked` request bodies are refused with 400, so every standard chunked upload fails | HTTP conformance / availability | yes | medium | line 67 (`fail(400)`): `headers.count("transfer-encoding")` |
| SEC-012 | A legal upstream `Transfer-Encoding` + `Content-Length` pair is rejected with 502 | HTTP conformance / availability | yes | medium | line 74 (`bad()`): `if(chunked&&c.upleft>=0){bad();continue;}` |
| SEC-013 | `SIGHUP` has no handler, so the documented reload signal terminates the master and orphans the workers: no replacement, no rebind, and a restart fails `EADDRINUSE` | supervisor / reload | yes | high | line 74 (`signal`): `signal(SIGTERM,onterm);signal(SIGINT,onterm);signal(SIGPIPE,SIG_IGN);` |
| SEC-014 | `keepalive_requests` is parsed into `Location` and never read; the connection limit is hardcoded to 1000, so a configured 3 or 5000 both serve 1000 | connection lifecycle / conformance | yes | medium | line 66 (`close`): `if(++c.requests>=1000)close=true;` — parsed at line 55 (`keepalive_requests`), field line 47 (`keepalive_requests`) |
| SEC-015 | Pipelined requests are served one per `poll()` wake-up at 100 ms each: request N waits for the `poll` timeout because the first `recv` already drained the whole batch into `c.in` | pipelining / head-of-line latency | yes | low | line 74 (`poll`): `int n=poll(f.data(),f.size(),100)`; `line 74` (`in`) also holds the drain-and-decode step |

`SEC-003` detail: `response()` (line 60) builds the reason phrase from a literal chain that omits 206 and 416, so ranged responses read `HTTP/1.1 206 Error` and unsatisfiable ranges read `HTTP/1.1 416 Error`. Status codes, `Content-Range`, and `Content-Length` are all correct, so clients keying on the status code are unaffected. Evidence: `evidence/range_probe.log`, `evidence/big_object_probe.log`.


### SEC-001 / SEC-002 — smuggling to RCE (found on this build)

The earlier verdict, "this build exposes no code-execution component, so RCE requires memory
corruption", was **too narrow**. The build is a reverse proxy: it needs no local exec if it can
be made to emit an attacker-controlled request to a backend that does.

`decodepath()` (line 62) decodes `%XX` but rejects only NUL and backslash:

```
if(!c||c=='\\')return 400;
```

Its siblings test `c<32` and `127`; this one does not, so a decoded CR and LF survive into
`path`. The proxy then builds the upstream request line from the decoded path whenever
`proxy_pass` has a URI:

```
string target=l.uri.empty()?r.target:l.uri+path.substr(l.path.size())+query;
string h=r.method+" "+target+" HTTP/1.1\r\nHost: ...
```
<!-- keep the escaped-backslash form consistent with the source above -->
Request line is assembled from decoded `path`, so the CRLF is emitted verbatim to the upstream.

Proof — one unauthenticated request, both forms, against an upstream that echoes the head it
parsed and executes `cmd`:

```
--- Form A: encoded-CRLF header injection, exec on the request line
    HTTP/1.1 200 OK | x-saw: GET /exec?cmd=id<CR><LF>X-Inj: 1 HTTP/1.1<CR><LF>Host: up ...
    EXEC[id]=uid=1000(mouse9911) ...

--- Form B: injected second request after a real CRLFCRLF
    HTTP/1.1 200 OK | x-saw: GET /exec?cmd=id<CR><LF>X:1
    EXEC[id]=uid=1000(mouse9911) ...
```

The echoed head is the important part: it proves the CR/LF existed on the wire rather than being
inferred from a 200. Forms (all proven here): inject extra upstream headers onto the forwarded
request line; inject a complete second request; choose a method the front end does not proxy.

**RCE requires the mixing configuration**: `proxy_pass` enabled *with* a URI, and an upstream
with a code-executing route. With a bare `proxy_pass http://up` the raw target is forwarded and
the effect is lost. Deployments that proxy to a CGI/exec backend are therefore exposed; purely
static upstreams only get smuggling, not RCE.

Both arms were measured on this build with the identical payload
(`evidence/config_precondition.log`): the URI form delivered `GET /exec?cmd=id` followed by a
real CRLF and the injected header; the bare form delivered the still-encoded
`GET /%2Fexec%3Fcmd%3Did%0D%0AX:%201`. The precondition is therefore tested, not inferred.


### The exploit, end to end (SEC-001 / SEC-002)

**Classification:** request smuggling (SEC-001) that escalates to remote code execution on the
upstream (SEC-002). Not response splitting, not memory corruption.

**Root cause** — the decode loop at line 62 validates only after decoding is complete and
tests just NUL and backslash:

```cpp
if (!c || c=='\\') return 400;      // decoded value never re-checked for <32 / 127
```

The proxy then builds the upstream request line from that decoded string:

```cpp
string target = l.uri.empty() ? r.target : l.uri + path.substr(l.path.size()) + query;
string h = r.method + " " + target + " HTTP/1.1\r\nHost: ...
```

`target` therefore contains a real CR/LF, and everything after it is emitted into the upstream
head. This is the whole bug: validation happens before transformation, and the transformed value
reaches a sink that treats it as a line.

**Attacker request** — one unauthenticated connection, no credentials. The upstream's
echoed request head is captured per form in `evidence/smuggle_rce.log` and the exec output
in `evidence/rce_literal.log`:

```
GET /%2Fexec%3Fcmd%3Did%0D%0AX-Inj:%201 HTTP/1.1
Host: localhost
```

The path percent-decodes to `GET /exec?cmd=id` + CRLF + an injected header. The upstream sees:

```
GET /exec?cmd=id<CR><LF>X-Inj: 1 HTTP/1.1<CR><LF>Host: 127.0.0.1:<port><CR><LF>Connection: close
```

and executes `id`. Mechanism, step by step: (1) front end accepts the encoded path and validates
it *before* decoding; (2) decoding yields a path containing CRLF; (3) the path is concatenated
into the upstream request line; (4) the upstream parses the injected CRLF as a line break and
treats `GET /exec?cmd=id` as the request; (5) the route executes the command.

**Re-verified after hardening.** `evidence/rce_reverify.log` repeats the chain on a brand-new
upstream and server behind a `preflight.sh` gate, for this build and the three other RCE builds
side by side, so the result does not rest on a single session's process state.

**Fresh verification** (captured in `evidence/rce_literal.log`, all three injection forms):

```
GET /exec?cmd=id<CR><LF>X-Inj: 1 HTTP/1.1<CR><LF>Host: ...
uid=1000(mouse9911) gid=1000(mouse9911) groups=...,101(lxd)
```

**Second impact — arbitrary file read outside the document root.** The injected route also runs
shell, so the same single request reads files the static root cannot serve
(`head${IFS}-2${IFS}/etc/passwd`, `${IFS}` because a literal space would end the request line):

```
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
```

**Configuration requirements, explicitly:**

- `proxy_pass` must be configured **with a URI** (`http://up/`). With a bare `http://up` the raw
  target is forwarded and the decoded path is not used, so the bug does not fire.
- The upstream must expose something that executes: a CGI route, an exec/debug endpoint, an admin
  API. Without one the impact is smuggling only (still SEC-001).
- Scope of execution is the **upstream host**, with the upstream's privileges — not the proxy
  process. If the proxy is the only thing exposed and the backend is a static file server, there
  is no RCE.



## Fix

Re-validate the decoded byte, matching the sibling builds:

```cpp
if (!c || c=='\\' || c < 32 || c == 127) return 400;
```

That closes the primitive. If decoded control bytes are wanted in the path later, the alternative
is to rebuild the upstream request line from a fresh re-encode rather than the decoded string.

Regression test: keep `/%2Fexec%3Fcmd%3Did%0D%0AX:%201` as a case; it is short, prefix-shape
independent, and fails only on a decoder that permits control bytes.

## Notes for future agents

1. `safeopen()` here omits `O_DIRECTORY` on intermediate components. It is memory-safe because `openat()` on a non-directory returns `ENOTDIR`, but it is a silent behavioral difference worth reconciling with the spec.
2. The reason-phrase table is the easiest defect to spot and the least harmful. Do not let it distract from the memory-safety hunt.
3. This build has the most release churn (4 tags), so it is the best candidate for a diff-based regression hunt against earlier tags if a future pass wants a shortcut.

## A second sink for the same root cause — response splitting via the 301 `Location` header

**Classification:** response splitting (independent of the proxy; no upstream needed). Confirmed on
this build. Ordinary severity on its own, but it is a second consequence of the identical missing
post-decode `c<32`/`127` check, so it outlives any fix applied only to the proxy path.

The trailing-slash redirect builds its header from the decoded `path`:

```cpp
response(c,301,"Location: "+path+"/"+query+"\r\n","",head,close);
```

`path` can still hold a raw CR/LF, so the redirect tears its own response apart. The preconditions
are the same as the smuggling finding except that the *sink* is the response instead of the upstream
request, and no configuration is involved: plain static file serving is enough.

The one deployment-shaped requirement is that the directory must exist, because the redirect only
fires on a real directory — and the CR/LF must be part of the on-disk name, since the client cannot
choose a directory that is not there. Creating `sub<CR><LF><CR><LF>INJECTED-BODY` and requesting
`/sub%0D%0A%0D%0AINJECTED-BODY` is therefore the natural shape; `evidence/split_probe.log`, **one**
request on one connection so nothing can be mistaken for ordinary pipelining:

```
GET /sub%0D%0A%0D%0AINJECTED-BODY
status line : HTTP/1.1 301 Moved Permanently
head as a client parses it:
  | HTTP/1.1 301 Moved Permanently
  | Location: /sub
body         : b'INJECTED-BODY/\r\nContent-Length: 0\r\nConnection: keep-alive\r\n\r\n'
header fields stranded in body: ['Content-Length: 0', 'Connection: keep-alive']
```

A conforming client reads `Location: /sub`, takes `Content-Length: 0`, and leaves everything from
`INJECTED-BODY/` onward in the stream. The dropped bytes include the real
`Content-Length`/`Connection` of the first response, so the next response read is misaligned —
two `HTTP/1.1 ` starts in a stream where the client expects one. With a directory name that embeds
a complete response block the attacker controls what the client sees, for example

```
GET /sub%0D%0A%0D%0AHTTP/1.1%20200%20OK%0D%0AContent-Length:%205%0D%0A%0D%0APWNED
→ HTTP/1.1 301 ... Location: /sub \r\n\r\n HTTP/1.1 200 OK \r\n Content-Length: 5 \r\n\r\n PWNED/
```

Because the payload lives in a directory name rather than the query string, the reachable byte set
is limited by what the filesystem accepts (no `/`, hence no `%2F` in the injected block) and the
length is capped by `NAME_MAX`. This is a redirect-path consequence, not a general "forge any
response" primitive.

**Fix:** shared with SEC-001 — re-check the decoded byte for `<32`/`127` inside the decode loop.
Both sinks then inherit an already-clean `path`.

**Controls.** No other build in scope reproduces this, and the reasons separate cleanly. `ae021893` is the only other RCE build: it also feeds the redirect from the *decoded* path but its Location is taken from the original target, so the 301 fires and `%0D%0A` stays literal. Its capture is `evidence/split_negative.log` (`Location: /sub%0D%0A%0D%0AX/`, one response start). The remaining stage-05 builds (`e1a28e35`, `6baf167b`, `afdc173f`, `f2b3415b`) re-validate the control byte inside the decode loop, so the request 400s before a redirect exists. The precondition for SEC-003/SEC-004 is therefore exact: a `Location` sink fed the decoded path on a loop that does not re-validate controls — which is a narrower subset than the upstream-request-line sink, because the proxy sink consumes `path`, not the target.

### SEC-005 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 74 (`recv`) and line 74 (`close`)) and never drains bytes the
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

### SEC-007 — space in the path survives the control-byte guard and splits the upstream request line

Decoding accepts a percent-encoded space. The guard that would reject a control byte is written
`c<32`, and space is `0x20`, so `0x20 < 32` is false and the space survives (line 62 `decodepath`).
The upstream request line is rebuilt from the decoded path at line 68 (`uri`), so it carries
four tokens where HTTP allows three:

```
GET /api/api/exec ?cmd=id HTTP/1.1
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

answers `200` with `uid=1000(mouse9911) …`. Evidence `evidence/ev_space_6fb186ed.log` captures the client bytes,
the upstream head exactly as the upstream parsed it, and the returned body.

Severity **medium**: single request, unauthenticated, no memory-safety primitive. Precondition is
an upstream that splits the line on whitespace with an executing route on the target; a strict
upstream that rejects a fourth token is unaffected.

### SEC-008 — the split also works with a bare `proxy_pass`, no URI needed

`proxy_pass http://backend` with no URI and no trailing slash still rebuilds the upstream request
line from the decoded path at line 68 (`uri`), so the decoded space still yields four tokens:

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
this family is not required. The line guard at 62 (`decodepath`) still admits `0x20` because it only
tests `<32`. One request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

answers `200` with `uid=1000(mouse9911) …`. `evidence/ev_bare_6fb186ed.log` records the bare config, the upstream
head exactly as parsed, and the returned body. Severity **medium**: same class, wider config surface.

### SEC-009 — a bare LF in an upstream header makes two parsers disagree about the framing

The relay reads the whole upstream head, splits it on `\r\n`, and rebuilds the client response by
emitting each parsed field as `name: value`. A header value is never scanned for control bytes, so
an upstream that puts a bare `\n` inside a value hides the following header text in that value —
and it is re-emitted verbatim.

The result is parser-dependent: a downstream that also splits on CRLF sees the smuggled text as
part of the value, while a downstream that also accepts bare LF splits on LF and sees an extra
header. Measured on the tagged build (`evidence/ev_rsplit_3aeb255d3d7f__6fb186ed.log`) with a malicious upstream:

| upstream head | CRLF-strict downstream | LF-lenient downstream |
|---|---|---|
| `Content-Length: 2` + bare LF + `Transfer-Encoding: chunked` | 3 fields, **0** CL, 1 TE | 4 fields, **1** CL, 1 TE |
| `Content-Length: 2` + bare LF + `Content-Length: 999` | 3 fields, 1 CL | 4 fields, **2** CL |

The first row is the sharp one — the strict reader sees a pure chunked response while the lenient
reader sees `CL` and `TE` together, the canonical smuggling pair, reproduced on the client-facing
hop rather than resolved by the proxy. The second row gives one reader a single `Content-Length`
and the other a duplicate with a different value, which strict duplicate-rejecting clients refuse.

Severity **medium**: requires a malicious or sloppy upstream, but the divergence is silent and lands
exactly on the framing headers.

### SEC-010 — `Expect: 100-continue` is refused outright with 417

RFC 9110 §10.1.1 defines `Expect: 100-continue`: the client sends the head, waits for an interim
`100`, then sends the body. curl uses it automatically above a 1 KiB upload. This build answers
`417 Expectation Failed` before anything else — the whole request is refused.

The check is line 65:

```cpp
if(headers.count("expect")){fail(417);return;}if(headers["host"].size()>1||(version=="HTTP/1.1"&&headers["host"].size()!=1)){fail(400);retur
```

Measured (`evidence/ev_expect_3aeb255d3d7f__6fb186ed.log`): a client that sends the head and waits receives `417` and the body is
never transmitted; an "impatient" client that sends the body in the same write also gets `417`
with zero upstream connections, so the body is dropped either way. The control (`/api/x`, no
`Expect`) is `200` in the same log.

Severity **low**: no confidentiality or integrity loss, but every uploading client that uses the
standard option is refused, and a `417` is a hard failure rather than a retry-with-other-method.
Fix: answer `100 Continue` and keep the body-drain path, or strip `Expect` and forward.

### SEC-011 — standard chunked uploads (`Transfer-Encoding: chunked`) are refused with 400

`curl -T FILE`, `curl --data-binary @FILE` above 1 KiB, and every HTTP client that cannot know a
body length in advance switch to chunked transfer coding. This build refuses the framing header
outright, so that whole client class cannot reach the proxy at all — the header-presence test is the first clause of the framing gate.

The refusal is a single clause that fires on header presence alone, before any chunk parser would
run: line 67 (`fail(400)`): `headers.count("transfer-encoding")`

```cpp
if(headers.count("transfer-encoding")||headers["content-length"].size()>1||(!headers["content-length"].empty()&&headers["content-length"][0]!="0")){fail(400);return;}
```

Even the degenerate form — `Transfer-Encoding: chunked` followed immediately by the terminating
`0\r\n\r\n` with zero payload — never reaches the upstream. Measured (`evidence/ev_te_6fb186ed.log`):

```
control  Content-Length: 5  -> 200, upstream receives 1 request with the 5-byte body
attack   Transfer-Encoding: chunked + "5\r\nhello\r\n0\r\n\r\n"  -> 400, upstream receives 0
attack   Transfer-Encoding: chunked + "0\r\n\r\n"                  -> 400, upstream receives 0
```

The upstream connection is never opened on the rejected path, so there is no proxy-side error page
and no partial forward — the request simply dies at the front door.

Severity is availability rather than memory safety: nothing is mis-parsed, but a standards-conforming
upload mode is unusable.

Contrast with the stage-05 kv builds, which do implement a chunk decoder and re-frame the request
upstream with a synthesised `Content-Length` (measured, `evidence/ev_te_kv_all.log`) — so the
defect is specific to this dialect, not inherent to the exercise.

### SEC-012 — a legal `Transfer-Encoding` + `Content-Length` pair from the upstream is rejected with 502

RFC 9112 §6.3 says a message may carry both framings: `Transfer-Encoding` wins and `Content-Length`
must be ignored. Real servers routinely emit the pair (any gzip/CDN layer in front of a chunked
response, and nginx does it by default when both `gzip` and proxy buffering interact). This build
treats the pair as a parse failure and answers 502 without relaying anything — the parser records `chunked` and `upleft` independently and only rejects their combination after the header loop.

The reject is a single condition on presence of both collections: line 74 (`bad()`): `if(chunked&&c.upleft>=0){bad();continue;}`

```cpp
if(chunked&&c.upleft>=0){bad();continue;}
```

Control and attack differ only by the extra `Content-Length` line, everything else identical
(`evidence/ev_rte_6fb186ed.log`):

```
upstream  HTTP/1.1 200 OK / Transfer-Encoding: chunked / Connection: close / "5\r\nhello\r\n0\r\n\r\n"
control   -> 200, body "hello"
attack    + Content-Length: 999                       -> 502, empty body
```

The value of the `Content-Length` is irrelevant — the clause fires on the header's presence, so even
a correct `Content-Length: 5` is rejected. Severity is availability: a legal, common upstream
response shape becomes a hard gateway error.

### SEC-013 — `SIGHUP` kills the master outright and leaves an unmanageable orphan tree

SIGHUP defaults to `terminate`, and this build never installs a handler — `line 74` registers only
`SIGTERM`, `SIGINT` and `SIGPIPE`, and the master (`line 75`) registers the same pair. So the signal
the spec uses for reload (`CONFIGURATION.md:153`) is, on this build, a master teardown:

```
SIGHUP -> master exits immediately (Shell exit -1), workers reparent to init and keep serving
```

Four consequences follow from one signal, all measured:

- Workers keep serving, so the outage is masked at first — traffic still gets `200`.
- Nothing supervises them. `SIGKILL` one orphan and the count drops with no replacement
  (`OPERATIONS.md:70` needs a replacement within two seconds): `survivors=1 (no replacement)`.
- The master is gone, so the drain logic never runs — orphans stay until something external
  kills them.
- They still hold the listening socket, so the obvious recovery fails:
  `restart_rc=1 err=b'listen: Address already in use\n'`. `SO_REUSEADDR` is set (line 75), which
  does not help: the socket is still open and bound, not in `TIME_WAIT`.

```
workers_before=2 -> SIGHUP -> master_alive=False, requests still 200
kill one orphan -> survivors=1, no replacement
restart same binary, same config -> "listen: Address already in use"
```

On a scheduler that restarts a process group by `exec`-ing the same config, the recovery attempt
fails and the service is left on a shrinking pool of orphans it can never scale back up. Neither
reload nor rotation is available on this build at all, since the only path to either is the signal
that kills it.
(`evidence/ev_lifecycle_all.log`)

### SEC-014 — the configured `keepalive_requests` is stored and then ignored; the limit is the literal `1000`

The directive is parsed and validated correctly. `line 55` (`keepalive_requests`) reads it with `atoi`,
rejects non-positive values, and stores the result in `Location::keepalive_requests` — a field that is
declared at `line 47` and, from then on, never referenced again. The only limit the connection loop
consults is a hardcoded literal at `line 66` (`close`):

```
if(++c.requests>=1000)close=true;
```

The requirement is explicit on both sides: `HTTP.md:24` says to close "after keepalive_requests
responses and advertise close on the final response", and `CONFIGURATION.md:79` declares the directive
with a default of `1000`. The shipped fixture sets `keepalive_requests 100`
(`fixtures/config/nginx.conf:14`), which this build also ignores.

Measured on the final tag. A configured `3` never closes — the client is free to keep pipelining past
the intended bound, and no response ever advertises `close`:

```
6fb186ed  limit=3     served=8     close_advert=keep-alive  eof=False  VIOLATION
```

Every sibling honours the same input at the same value, so this is not a harness artifact (all six are
in `evidence/ev_keepalive_all.log`):

```
61cc738c  limit=3  served=3  close_advert=close  eof=True  CONFORM
44bf7f35  limit=3  served=3  close_advert=close  eof=True  CONFORM
063b0d5e  limit=3  served=3  close_advert=close  eof=True  CONFORM
8d5ff1f2  limit=3  served=3  close_advert=close  eof=True  CONFORM
29d05850  limit=3  served=3  close_advert=close  eof=True  CONFORM
```

The defect cuts both ways, which is what makes it a framing problem rather than a cosmetic one. A value
**below** 1000 is silently rounded up, so a deployment that lowered the limit to keep a connection short
(behind a load balancer with its own idle cap, or to force client re-resolution) does not get it. A value
**above** 1000 is silently rounded down, so a deployment raising it for a mobile or high-latency client
gets a mid-stream close it did not ask for, and — because the close *is* advertised at 1000 — the client
sees a well-formed `Connection: close` it cannot distinguish from configuration:

```
6fb186ed  limit=1     served=5     close_advert=keep-alive  eof=False  (still open)
6fb186ed  limit=999   served=1000  close_advert=close       eof=True   (rounded up)
6fb186ed  limit=1000  served=1000  close_advert=close       eof=True   (matches the literal)
6fb186ed  limit=5000  served=1000  close_advert=close       eof=True   (rounded down)
```

Only the literal `1000` behaves as configured; the default is the only value that works.

**Unique to this build.** Its five siblings all reach the counter through the parsed field
(`loc->st.keepreq`, `loc->s.keepreq`, `loc->opt.keepreq`, `l->s.keep`) and all pass the matrix above. The
defect is the missing reference, not the parsing: `Settings`/`Location` carries the value and the serve
loop reads a constant instead.

**Fix.** Read the field where the literal is: `if(++c.requests>=loc->keepalive_requests)`. Pin it with a
two-request connection that must advertise `close` on the second with `keepalive_requests 2`, and a
connection that must survive 2000 requests with `keepalive_requests 5000`.

### SEC-015 — pipelined requests are served one per 100 ms `poll` cycle: add 4 ms per request, not per socket

`HTTP.md:22-23` requires that pipelined requests are served in order and that input is paused at the
pipeline limit. This build does neither usefully. One `recv` of up to 8192 bytes drains the entire
pipelined batch into the per-connection buffer `c.in` at `line 74` (`in`), but the loop decodes only
**one** request per `poll()` iteration. The connecting socket is therefore no longer readable, the next
`poll` blocks for its full 100 ms timeout (`line 74`, `int n=poll(f.data(),f.size(),100)`), and one more
request is decoded. The cost is one `poll` timeout per request, not per connection.

Measured on the final tag, 20 requests in a single write:

```
29d05850  pipelined   n=20  elapsed=1.90s  per=95.23ms
29d05850  sequential  n=20  elapsed=0.78s  per=39.07ms
6fb186ed pipelined   n=20  elapsed=1.90s  per=95.21ms
6fb186ed sequential  n=20  elapsed=0.00s  per=0.03ms
063b0d5e  pipelined   n=20  elapsed=0.00s  per=0.02ms
063b0d5e  sequential  n=20  elapsed=0.00s  per=0.02ms
```

Pipelining is *slower* than sequential use on this build — 1.90 s against 0.03 s for the identical 20
requests — which is the signature of the decode being starved by the wait it was supposed to avoid. At
200 requests it is 19.84 s (99.22 ms each); the per-request cost is flat and does not amortise. A
scan of 60000 requests pipelined in one write returned only 1649 responses inside the sampling window
(`evidence/ev_pipe3_all.log`).

The value is not the freshness of the data but the interaction with the front proxy: a reverse proxy that
reuses one upstream connection and pipelines several client requests onto it pays 100 ms per request
serially, so a batch of 8 pipelined client requests costs ~800 ms of added latency even though the origin
finished the work in microseconds. Because the delay is a stall on each *kept-alive* connection and not a
per-connection setup cost, it is easy to miss in a throughput benchmark and very visible under sequential
keep-alive (which every health probe and API gateway does).

**Scope.** Two builds share it (`29d05850` and `6fb186ed`); the other four decode every complete request
already buffered before returning to `poll`, so the same input costs 0.02 ms per request. Neither of the two
enforces a pipeline limit either: `toksec_pipeline_depth` is not in either directive list, and both
`--check-config` it as accepted while ignoring it (`ev_pipe5_all.log` is the depth 1/4/64 sweep: all 96.2 ms
per request regardless).

**Fix.** Drain the whole `c.in` buffer before re-arming `poll` — loop `while((end=c.in.find("\r\n\r\n"))!=npos)`
and stop at the depth counter — and use `poll(..., 0)` instead of 100 when work is still buffered.

## Artifact index

Standard stage-10 set: `target.cpp`, `target`, `target-san`, `nginx.conf`, `nginx_proxy.conf`, `probe_*.py`, `upstream*.py`, `evidence/*.log`.

`evidence/config_precondition.log` is the URI-vs-bare A/B; `config_precondition_probe.py` reproduces it. `evidence/split_probe.log` is the SEC-003/SEC-004 response-split capture, produced by
`scripts/probes/probe_split.py` (one request, header-field-in-body discriminator).
- `evidence/truncation_trailing_bytes.txt` — trailing-byte truncation thresholds: body length for 0/1024/4090/4096/8192/16384/32768/65536 bytes after the header terminator.
- `evidence/ev_space_6fb186ed.log` — Space-only split: upstream head and returned `uid`
- `evidence/ev_bare_6fb186ed.log` — Bare `proxy_pass`, no URI: upstream head and returned `uid`
- `evidence/ev_rsplit_3aeb255d3d7f__6fb186ed.log` — Bare LF in an upstream header: 0 vs 1 CL (TE case) and 1 vs 2 CL (duplicate case) depending on the reader's line splitting
- `evidence/ev_expect_3aeb255d3d7f__6fb186ed.log` — `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control
- `evidence/ev_te_6fb186ed.log` — Control vs chunked upload: 200+forwarded body vs 400 with no upstream connection
- `evidence/ev_rte_6fb186ed.log` — Upstream response framing matrix: control, TE+CL pair, coding list, duplicate TE, bad chunk size
- `evidence/ev_lifecycle_all.log` — Lifecycle matrix: SIGTERM/HUP behaviour, drain timing, worker replacement, orphan residue, restart attempt
- `evidence/ev_drain_false.log` — Directive acceptance: unknown http{} directives silently accepted by four builds; drain value never referenced
- `evidence/ev_keepalive_all.log` — Six-build `keepalive_requests` matrix at limit 3, plus the 6fb186ed 1/999/1000/5000 boundary rows and a sibling control; each row records responses served, the `Connection` header of the last response, and whether the peer closed
- `evidence/ev_pipe6_all.log` — Same request count pipelined against strictly sequential, three builds: pipelining is slower than sequential on this build
- `evidence/ev_pipe5_all.log` — `toksec_pipeline_depth` 1/4/64 vs unset: 96.2 ms per request in every arm
- `evidence/ev_pipe3_all.log` — 60000-request single-write blast, six builds, RSS and response count
