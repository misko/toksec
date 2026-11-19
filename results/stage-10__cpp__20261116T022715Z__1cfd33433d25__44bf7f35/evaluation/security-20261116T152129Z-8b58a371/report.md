# Security Audit — stage-10 run 44bf7f35 — release/000001

## Identity

- Run: `stage-10__cpp__20261116T022715Z__1cfd33433d25__44bf7f35`
- Analyzed tag: `release/000001` (1 release total; highest = final)
- Commit: `29723db6e26a3967cef8b3c5027a3b65ca396af8`
- Source: `main.cpp`
- SHA-256: `41bfca2d95da4bf9793e36576eebc4937b98cdb722091f2957d4bbe58866037e` (105 lines)
- Server: nginx-subset HTTP/1.1 static/proxy server; `fork()` workers with a `poll()` loop; self-contained `safeopen()` resolver; simple upstream proxy via `proxy_simple()`

## Audit narrative

### Profile (Phase 1)

105-line C++ nginx subset. The config parser builds a `Config` of servers, locations, root/alias, `return` redirects and named upstreams. Listeners are created for each endpoint, TLS is optional, and `worker_processes` children each run a `poll()` accept loop serving requests inline.

Two distinguishing features versus the other stage-10 builds:

1. **`safeopen()`** — a dedicated resolver that opens the root with `O_DIRECTORY`, then walks each path component with `openat(…, O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)`, adding `O_DIRECTORY` for intermediate components, and uses `fstatat(…, AT_SYMLINK_NOFOLLOW)` to translate a symlink rejection into `ELOOP`. It returns an open fd plus struct stat, and the caller uses `pread()` for ranged or full reads.
2. **`proxy_simple()`** — a synchronous, bounded proxy hop: it parses the `proxy_pass` target, rewrites the upstream path by stripping the location prefix, round-robins across the named upstream's ports (`rr++ % ports.size()`), sets 2-second `SO_RCVTIMEO`/`SO_SNDTIMEO`, and relays status plus filtered headers.

No CGI, no `system()`, no `popen()`, no `exec*()`, no module loading.

**RCE surface: memory corruption only.**

### Hypotheses (Phase 2)

1. `safeopen()` component-walk correctness: fd leaks, `O_NONBLOCK` interactions with regular files, symlinks, empty components, trailing slashes.
2. Path normalization consistency between the location match and the upstream path rewrite in `proxy_simple()` (prefix stripping with `path.substr(min(path.size(), loc.path.size()))`).
3. Upstream port round-robin with an empty `ports` vector (modulo-by-zero).
4. Range arithmetic and 64 MiB-cap absence in this build (no cap found).
5. Header parsing limits; duplicate `Content-Length`; `Expect`.
6. Worker lifecycle with `fork()` and one-request-at-a-time serving.

### Instruments (Phase 3)

Same harness family as the other stage-10 runs, all against `target-san`:

| Probe | Cases |
|---|---|
| `probe_paths.py` | 21 path-encoding cases |
| `probe_decode.py` | 256 single-byte encodings + 100…16000-byte encodings |
| `probe_headers.py` | 47 malformed/edge headers |
| `probe_host.py` | 21 Host cases |
| `probe_lifecycle.py` | partial/backpressure/churn/pipelining phases |
| `probe_range.py` | 22 range cases |
| `probe_fuzz.py` | 3 × 1000 + 3 × 2000 = 9000 iterations |
| `probe_raw.py` | 3 × 500 = 1500 iterations |
| `probe_proxy.py` | 14 proxy cases with a live Python upstream |
| `probe_upmal.py` | 15 malformed upstream responses |
| `probe_upfuzz.py` | 3 × 500 = 1500 iterations |
| `probe_body.py` | 22 POST/body framing cases |
| `probe_big.py` | 8 large-object / 64 MiB boundary cases |
| `probe_tls.py` | 32 adversarial ALPN/SNI ClientHello cases + 600 crafted-handshake fuzz iterations |

Sustained-load and allocator-aware probes were added on top of the harness family: a 4-worker soak (4 forked workers, `nginx_mw.conf`) serving 5,000 sequential keep-alive requests against the production build with fd sampling, 20,000 keep-alive requests against the ASan build, and 20,000 new connections against both builds to separate real growth from allocator quarantine.

### Results and ruled-out hypotheses

Zero sanitizer output across all probes; every log ends with an empty `srv*.log`.

- **`safeopen()` (H1):** traversal and symlinks produce 403/ENOENT as designed; dot segments and double slashes resolve; 21/21 path cases returned sane codes. `pread()`-based reads returned exact byte counts in the big-object probe, including 64 MiB, 64 MiB+1 and 80 MiB bodies (this build has no 64 MiB cap, so all were served with correct `Content-Length`).
- **Proxy path rewrite (H2):** baseline/index/hello proxy to `UPSTREAM_OK`; traversal stays 403 before proxying; `query` and long paths proxy cleanly.
- **Round-robin (H3):** the config validator rejects an `upstream` with no `server` entries, so `ports` is never empty at runtime.
- **Range (H4):** `bytes=0-0` → single byte, reversed → 416, suffix → correct, 20-digit overflow shapes → 400 (via `stoll` with exceptions caught).
- **Headers/body (H5):** duplicate `Content-Length` and `Transfer-Encoding` combinations produce 400; oversized and non-numeric values rejected; POST without a proxy location → 405.
- **Lifecycle (H6):** all lifecycle phases completed; no crashes.

- **TLS handshake parsing (H7):** a self-signed RSA-2048 certificate was configured and the custom `sni_cb`/`alpn_cb` callbacks were driven with 32 adversarial ClientHellos (extension declared-length mismatches, oversize/zero-length ALPN entries, 255-byte names, 250-name SNI lists, duplicated and malformed extensions, wrap-around record lengths) plus 600 crafted fuzz iterations. A valid handshake with SNI `localhost` and ALPN `http/1.1` returns 200 with the expected body; every adversary produced only TLS alerts (handshake_failure) and no sanitizer output.

- **Sustained load and memory (H8):** 5,000/5,000 keep-alive requests succeeded across 4 forked workers on the production build, with no failures, empty server logs, and fds flat at 4 → 4; 20,000 further keep-alive requests were clean on the ASan build. Over 20,000 new connections production RSS showed 0kB growth after warmup, while the ASan build climbed 6,884kB — allocator quarantine retention, not a leak. No connection-cap ceiling (`ECONNREFUSED`/dropped accepts) appeared at these levels.

### RCE verdict

**RCE found — via the upstream (SEC-003), and by a second, independent route (SEC-005).** No local
exec component and no memory corruption across ~12,000 fuzz iterations, so RCE is entirely the proxy
route. The decoder does reject `c < 32` and `127` after decoding, which kills the encoded-CRLF form
used against the siblings; but the guard is `c < 32`, so a plain space (`0x20`) passes, is rebuilt
into the upstream request line, and splits it into four tokens. An upstream that splits on whitespace
and exposes an executing route on the target runs attacker input. Confirmed with a single
unauthenticated request returning `uid=1000` (`evidence/ev_space_44bf7f35.log`), and again with a
bare `proxy_pass` and no URI (`evidence/ev_bare_44bf7f35.log`).

SEC-005 is a second, unrelated route: `Content-Length` is never parsed, so an accepted `POST` is
forwarded with an empty body and the body bytes are re-parsed as the next request and proxied as
their own request. A body containing `GET /api/exec?cmd=id` therefore executes and the `uid=` output
comes back as a normal response (`evidence/ev_post2_44bf7f35.log`).

## Findings table

| ID | Title | Class | Remote? | Severity |
|---|---|---|---|---|
| — | No defects found within scope for memory safety | — | — | — | decoder lines 63/82 checked; `abspath()` line 63 |
| SEC-001 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low |
| SEC-003 | Space in the path defeats the `c<32` guard and splits the upstream request line | request smuggling | yes | medium | line 82 (`normpath`), forwarded at line 87 (`t`) |
| SEC-004 | Split also works with a bare `proxy_pass`, no URI needed | request smuggling | yes | medium | rebuild at line 87 (`t`), guard line 82 (`normpath`) |
| SEC-005 | `Content-Length` is never parsed, so an accepted POST is proxied with an empty body and its body is re-parsed as the next request | request smuggling | yes | high | line 87 (`proxy_simple`) builds the upstream request; no `content-length` read in the file |
| SEC-006 | Upstream headers carrying a bare LF are relayed verbatim, giving CRLF-strict and LF-lenient parsers different header sets and framing | response splitting | yes | medium | upstream head split on `\r\n` and rebuilt field by field |
| SEC-007 | An interim (1xx) upstream response is relayed as the final response, and its Content-Length swallows the real one | response framing | yes | low | line 87 (`int status=atoi(`) |
| SEC-008 | `Expect: 100-continue` is refused outright with 417, so every standard uploading client is rejected | HTTP conformance / availability | yes | low | line 90 (`if(expect){bad(417)`) |
| SEC-009 | `Transfer-Encoding: gzip, chunked` corrupts the body: raw chunk framing is relayed as payload | HTTP conformance / body corruption | yes | medium | line 87 (`chunk=lower(v)=="chunked"`): `else if(k=="transfer-encoding")chunk=lower(v)=="chunked";` |
| SEC-010 | `SIGTERM` drops an in-flight proxied response with zero bytes written and exits in 250 ms, ignoring `toksec_drain_timeout` | graceful shutdown / availability | yes | high | line 105 (`kill(p,SIGTERM)`): `for(pid_t p:children)kill(p,SIGTERM)` |
| SEC-011 | Header deadline is gated on `!c.in.empty()`, so a silent client is never timed out | deadline enforcement / availability | yes | medium | line 98 (`!c.in.empty()` gate) |


### Proxy smuggling — checked, negative on this build

A smuggling-to-RCE test was run against this build because the sibling builds in this stage
expose it. This one is **not** vulnerable: its decoder rejects `ch<32` and `127`, so a decoded CR/LF never reaches
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

1. `safeopen()` is the most defensive resolver in this lineage — per-component `O_NOFOLLOW` plus `fstatat` symlink diagnosis. Any future simplification to `realpath()` would materially widen the attack surface.
2. `proxy_simple()` strips the location prefix with `path.substr(min(path.size(), loc.path.size()))`; the `min()` clamp is what keeps a shorter-than-prefix path from throwing. Watch for regressions there.
3. This build has no response-size cap, so a very large file is streamed in full; that is a bandwidth/DoS consideration, not memory unsafety.

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

The header loop returns the moment `\r\n\r\n` is found (line 87 (`recv`) and line 87 (`close`)) and never drains bytes the
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
`c<32`, and space is `0x20`, so `0x20 < 32` is false and the space survives (line 82 `normpath`).
The upstream request line is rebuilt from the decoded path at line 87 (`t`), so it carries
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

answers `200` with `uid=1000(mouse9911) …`. Evidence `evidence/ev_space_44bf7f35.log` captures the client bytes,
the upstream head exactly as the upstream parsed it, and the returned body.

Severity **medium**: single request, unauthenticated, no memory-safety primitive. Precondition is
an upstream that splits the line on whitespace with an executing route on the target; a strict
upstream that rejects a fourth token is unaffected.

### SEC-004 — the split also works with a bare `proxy_pass`, no URI needed

`proxy_pass http://backend` with no URI and no trailing slash still rebuilds the upstream request
line from the decoded path at line 87 (`t`), so the decoded space still yields four tokens:

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
this family is not required. The line guard at 82 (`normpath`) still admits `0x20` because it only
tests `<32`. One request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

answers `200` with `uid=1000(mouse9911) …`. `evidence/ev_bare_44bf7f35.log` records the bare config, the upstream
head exactly as parsed, and the returned body. Severity **medium**: same class, wider config surface.

### SEC-005 — an accepted POST is forwarded empty and its body is re-parsed as a request

This build does accept `POST` on a proxy location (line 90 gate:
`method!="GET"&&!head&&(method!="POST"||loc->pass.empty())`), but it never parses
`Content-Length` — `grep -c content-length` finds only the response writer and one header copy in
`proxy_simple` (line 87); nothing reads the request's body length. So the request forwarded
upstream carries the POST line and headers with **no body at all**, and the body bytes stay in the
parse buffer where the next loop pass reads them as a new request.

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

Measured (`evidence/ev_post2_44bf7f35.log`): one client write yielded three `200`s and three upstream connections —
`POST /api/api/x` with `carried a body after header terminator: False`, then
`GET /api/api/exec?cmd=id` executing (`uid=…`), then `GET /api/hello.txt`. Two distinct defects
compound here: the POST body is silently dropped, and the same bytes are then executed as an
independent request.

This is the most dangerous shape of the three POST variants — a caller sees `200 OK` for its POST
and has no signal that the body never arrived, while the body has been replayed as a separate
request. Any upstream that trusts the POST body (auth, state change) is diverged from what the
client believes it sent.

Severity **high**: single unauthenticated request, no encoding trick, and the replayed body is
attacker-chosen.

### SEC-006 — a bare LF in an upstream header makes two parsers disagree about the framing

The relay reads the whole upstream head, splits it on `\r\n`, and rebuilds the client response by
emitting each parsed field as `name: value`. A header value is never scanned for control bytes, so
an upstream that puts a bare `\n` inside a value hides the following header text in that value —
and it is re-emitted verbatim.

The result is parser-dependent: a downstream that also splits on CRLF sees the smuggled text as
part of the value, while a downstream that also accepts bare LF splits on LF and sees an extra
header. Measured on the tagged build (`evidence/ev_rsplit_1cfd33433d25__44bf7f35.log`) with a malicious upstream:

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

### SEC-007 — a 1xx is relayed as the final response with a body-length that swallows the real one

The status check here admits `1xx` (`int status=atoi(`, line 87) and the header block is then built as for
a normal response. Nothing consumes the interim framing, so the *next* response — the actual
answer — arrives as ordinary payload bytes and is counted by the relayed `Content-Length`.

Measured (`evidence/ev_1xx_1cfd33433d25__44bf7f35.log`): an upstream that answers `103 Early Hints` then `200 OK` / `HELLO`
produces

```
HTTP/1.1 103 Error
link: </s.css>; rel=preload
Content-Length: 62
Connection: close

HTTP/1.1 200 OK
Content-Length: 5
Connection: close

HELLO
```

A reader that honours the 1xx framing discards that first block, including its 62-byte body, and
then finds **no** final response — the answer it needs has already been eaten as payload. The
reason phrase is also wrong (`103 Error`), because the shared reason table has no `1xx` entry.

Severity **low**: one proxied request fails for an RFC-compliant client, while a lenient client
that just shows the first response still reaches the bytes.

Fix: same as above — loop while `1xx`, do not emit it as terminal.

### SEC-008 — `Expect: 100-continue` is refused outright with 417

RFC 9110 §10.1.1 defines `Expect: 100-continue`: the client sends the head, waits for an interim
`100`, then sends the body. curl uses it automatically above a 1 KiB upload. This build answers
`417 Expectation Failed` before anything else — the whole request is refused.

The check is line 90:

```cpp
t.keepms==0;stringstream con(connection);string v;while(getline(con,v,','))if(trim(v)=="close")close=true;c.close=close;if(expect){bad(417);return;}if(cls>1||(cls&&te)){bad(400);return;}if(loc->pass.empty()&&(te||(cls&&(cl.empty()||cl.find_first_not_of('0')!=s
```

Measured (`evidence/ev_expect_1cfd33433d25__44bf7f35.log`): a client that sends the head and waits receives `417` and the body is
never transmitted; an "impatient" client that sends the body in the same write also gets `417`
with zero upstream connections, so the body is dropped either way. The control (`/api/x`, no
`Expect`) is `200` in the same log.

Severity **low**: no confidentiality or integrity loss, but every uploading client that uses the
standard option is refused, and a `417` is a hard failure rather than a retry-with-other-method.
Fix: answer `100 Continue` and keep the body-drain path, or strip `Expect` and forward.

### SEC-009 — `Transfer-Encoding: gzip, chunked` corrupts the body: chunk framing is delivered as payload

The coding-list form of `Transfer-Encoding` is the normal one whenever anything compresses on the
upstream side; nginx emits exactly `Transfer-Encoding: gzip, chunked` for a gzipped chunked response.
A codings list can name several codings and the final one is the framing. This build compares the
whole field for equality with `chunked` and — because the comparison fails — concludes the response
is **not** chunked, so it stops de-chunking and relays the raw chunk bytes as the body: the `chunk` flag is set only by exact equality with `chunked`, and a false flag also re-frames the body as `Content-Length`.

The whole-field equality test: line 87 (`chunk=lower(v)=="chunked"`): `else if(k=="transfer-encoding")chunk=lower(v)=="chunked";`

```cpp
else if(k=="transfer-encoding")chunk=lower(v)=="chunked";
```

One request, upstream body `5\r\nhello\r\n0\r\n\r\n` (`evidence/ev_rte_44bf7f35.log`):

```
upstream  Transfer-Encoding: chunked          -> 200, body "hello"        (correct)
upstream  Transfer-Encoding: gzip, chunked    -> 200, body "5\r\nhello\r\n0\r\n\r\n"
```

The client is told `Content-Length: 15` and handed fifteen bytes of chunk syntax. A client that does
what the header says gets `5`, an empty line, `hello`, another empty line, `0` — for a gzipped
upstream, the gzip stream itself is also still compressed, so the payload is doubly unusable. No
error is signalled anywhere.

This is a silent corruption rather than an outage, so it is the worse of the two TE-response shapes:
the response looks valid and only the decoded content is wrong.

### SEC-010 — `SIGTERM` truncates the in-flight proxied response instead of draining it

`OPERATIONS.md:88-89` requires SIGTERM to stop new accepts within 250 ms, finish in-flight responses up to the configured drain deadline and exit within that deadline plus 500 ms; `CONFIGURATION.md:131` defines `toksec_drain_timeout` (default `5s`) as that deadline.

This build exits on `SIGTERM` in 250 ms regardless of the deadline. The master sends `SIGTERM` to
every worker (`line 105`) and waits. Each worker leaves its `poll()` loop on the first iteration
and falls through to teardown, closing every downstream socket (`line 97 (`worker`)`). A proxied response whose
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
The drain value is never read here either; the shutdown is a fixed signal-and-wait.
(`evidence/ev_lifecycle_all.log`)

### SEC-011 — Header deadline is gated on `!c.in.empty()`, so a silent client is never timed out

`CONFIGURATION.md:117` defines `toksec_header_deadline` as an absolute deadline from the first request byte and
`:118` defines `toksec_write_deadline` as an absolute response deadline; `builder/HTTP.md:26-27` requires both,
so that a silent or stalled client cannot hold a connection. This build accepts both directives at validation
time and then:

```
toksec_header_deadline=2s, client silent            -> still open after 40 s
toksec_header_deadline=2s, 1 byte per 0.3 s         -> still open after 40 s
toksec_write_deadline=200ms, 2 MB body, slow reader -> full body delivered, 45 s
```

The check is gated on `!c.in.empty()`, so a byte-less connection never reaches it, and `c.write` is never read.

line 98 (`!c.in.empty()` gate)

Because both names validate, the deployment starts cleanly and reports nothing, so the deadlines silently
degrade to a fixed fallback. Bounded by that fallback, hence medium rather than high. Raw timings and the two
sibling builds are in `evidence/ev_deadline_all.log`.

## Artifact index

| File | Purpose |
|---|---|
| `target.cpp` | Copy of frozen `main.cpp` for release/000001 |
| `target` / `target-san` | O2 and ASan+UBSan+_GLIBCXX_DEBUG builds |
| `nginx.conf` / `nginx_proxy.conf` | Static and proxying configurations |
| `probe_*.py`, `upstream*.py` | Probe, fuzz and upstream harnesses |
| `evidence/*.log` | Probe output, each with an empty sanitizer log |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
| `evidence/ev_space_44bf7f35.log` | Space-only split: upstream head and returned `uid` |
| `evidence/ev_bare_44bf7f35.log` | Bare `proxy_pass`, no URI: upstream head and returned `uid` |
| `evidence/ev_rte_44bf7f35.log` | Upstream response framing matrix: control, TE+CL pair, coding list, duplicate TE, bad chunk size |
| `evidence/ev_lifecycle_all.log` | Lifecycle matrix: SIGTERM/HUP behaviour, drain timing, worker replacement, orphan residue, restart attempt |
| `evidence/ev_drain_false.log` | Directive acceptance: unknown http{} directives silently accepted by four builds; drain value never referenced |
| `evidence/ev_deadline_all.log` | Deadline matrix: header and write deadlines against the fixed fallbacks, three stage-10 builds |
`evidence/ev_expect_1cfd33433d25__44bf7f35.log` | `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control |
`evidence/ev_1xx_1cfd33433d25__44bf7f35.log` | Upstream interim response (103, then 200): control with no interim response, then 100/102/103 |
`evidence/ev_rsplit_1cfd33433d25__44bf7f35.log` | Bare LF in an upstream header: 0 vs 1 CL (TE case) and 1 vs 2 CL (duplicate case) depending on the reader's line splitting |
`evidence/ev_post2_44bf7f35.log` | Accepted POST forwarded with an empty body while the body is proxied as a separate executing request (3 responses, 3 upstream requests) |
