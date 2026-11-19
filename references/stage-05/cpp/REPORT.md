# Stage 5 C++ reference

The current implementation is API validated. A coordinated supplemental native
full-matrix diagnostic exposed reliability failures in the preceding source;
the current source repairs proxy admission and pool validation. A later complete
diagnostic of the current source had zero errors in its first 23 workloads but
4037 client timeouts in the last workload. Its overall performance result remains
ineligible and the timeout cause is unresolved. This report distinguishes those
source versions.

Final source: `references/stage-05/cpp/main.cpp`

SHA-256: `2f868836bfd3e80cf23579b3def815b29bcc05f92dbbebba311e7e689ffdd0b3`

## Implementation

The server uses one nonblocking Linux epoll loop for downstream clients and
upstream connections. Each downstream connection processes one request at a time,
preserving pipeline order and pausing socket reads while producing a response or
awaiting an upstream. This keeps the active request queue below every positive
configured pipeline depth. Input arrives in bounded 16 KiB reads. Absolute header
and upstream deadlines and progress-based write deadlines are checked every
20 ms. Generation-tagged epoll registrations protect against reused descriptors.

Local routing opens every path component relative to its configured directory
descriptor, checks object types without following symlinks, and uses `O_NOFOLLOW`
and `O_NONBLOCK`. Files use sendfile with a separate offset per response. Index,
alias, host, redirect, ETag, MIME, conditional and range decisions operate on the
selected representation. Path decoding is strict UTF-8 and happens once.

Proxy uploads support bounded Content-Length and chunk decoding, including
extensions and bounded validated trailers. Upstream responses are fully decoded
and bounded before downstream headers begin. Known lengths are reserved exactly,
avoiding geometric string growth for 64 KiB benchmark responses. Healthy upstream
HTTP/1.1 connections are pooled by authority; each authority retains at most 256
idle connections. Pool entries validate both the descriptor's registration
generation and selected authority before reuse. Requests select upstreams round robin. GET/HEAD can retry once;
POST is never replayed. Hop headers and Connection-nominated fields are stripped
in both directions. HEAD preserves representation length where known and sends
no downstream body.

Uncached proxy requests enter a FIFO admission queue after their headers are
validated. There are 64 slots covering body upload, upstream exchange and
downstream response output. Additional clients pause reads with only their first
bounded input fragment retained. A slot stays assigned across a retry and is
released on response completion or disconnect. Release pumps the oldest queued
request before the same connection can submit another request. Queue nodes are
removed in constant time when a queued connection disconnects. Existing zero-body
cache hits need no upstream slot. This limits connection-attempt bursts, preserves
upstream connection reuse and bounds active noncached response buffers.

The response cache uses monotonic expiry, LRU eviction, body-byte accounting, an
additional 4 MiB estimated metadata budget, and a 4096-entry limit, including
empty-body entries. Keys include scheme, normalized routing host, target/query,
Accept-Encoding and representation-affecting range/conditional fields.
Authorization, Set-Cookie, private/no-store, unsupported Vary and zero-age cases
bypass storage. Cached bodies are shared with active responses rather than
copied. Eviction removes the entry's accounting; an active response can retain its
shared body until completion or its write deadline. Active uncached proxy request
and response buffers are bounded by `body_bytes` and the 64 admission slots.
Cached bodies retained by active cache-hit responses are shared; there is no
separate aggregate byte budget for all such retained shared bodies.

Configuration is validated into a complete snapshot before use. SIGHUP atomically
replaces a valid snapshot, flushes cache and idle upstream pools, and resets the
global monotonic token bucket. Invalid reloads retain the old snapshot. Responses
from an older snapshot cannot repopulate the new cache. Listener changes reject
reload. SIGTERM closes the listener immediately, finishes active responses until
the drain deadline and exits. Final responses half-close the write side and drain
available excess input for a bounded interval, preserving response bytes when a
client pipelines beyond max_requests.

Only the C++/C standard libraries and Linux/POSIX APIs are used. There are no
third-party dependencies, subprocesses, runtime-loaded libraries, encryption or
compression. Direct OS interfaces include epoll, sockets, openat/fstatat,
sendfile and signalfd. No C++ threads are created by the server.

## Validation evidence

Full API commands used the assigned correctness affinity:

```sh
taskset -c 8,23 python3 evaluate.py --section api --level 5 --language cpp --source references/stage-05/cpp/main.cpp --output .runs/references/stage-05-cpp/api-006
```

The retained final result is
`.runs/references/stage-05-cpp/api-006/result.json`: successful independent C++20
O3 compilation, **35/35 API checks passed**, no compiler or server diagnostics.
The result records the final source hash above. This covers inherited static,
persistent, routing and proxy checks plus cache, cache capacity, reload, rate
limiting, graceful stop, configured connection/write/pipeline limits, and invalid
configuration cases.

Earlier attempts remain available:

| Attempt | Source SHA-256 | Result |
|---|---|---|
| `api-001/result.json` | `6c4d11dca577b9791d0815661ebdd8f1e8add316fb3a0b784dac72550f88940c` | 35/35 API checks passed; initial implementation |
| `api-002/result.json` | `50b5c357222d54edb071c7f3cb142367f5a885c9ed20fdefe5c6a5bb65f8808c` | 35/35 passed after close, half-close, reload-cache and rate-body framing repairs |
| `api-003/ATTEMPT.md` and candidate build files | retained in candidate snapshot | Inconclusive infrastructure startup: trusted driver timed out waiting for its upstream fixture; API cases were not emitted |
| `api-004/result.json` | `bf7f184fb0f351daa959814e3dfecde3915594b0ee2339c2a153d72aaa07eb25` | 35/35 passed after cache metadata caps, exact response reservation and strict chunk-extension parsing; measured pre-repair source |
| `api-005/result.json` | `7fbd234c18cb1fb1a4ed790fa41069aeac291477c1cafcaef243696b2667e113` | 35/35 passed after FIFO proxy admission |
| `api-006/result.json` | final hash above | 35/35 passed after pool generation and authority validation |

All paths in the table are relative to
`.runs/references/stage-05-cpp/`. Every evaluator attempt retains its compiled
source snapshot and build diagnostics. The initial standalone compile was also
pinned to CPU 8.

Additional tests run against sandboxed candidates, with test-created upstream
listeners, are retained in `focused-001/` through `focused-008/`. Final
`focused-006/stdout.json` reports nine passing groups against the final api-006
candidate:

- 1000 pipelined requests with max_requests=2: both final response bodies and
  clean EOF survive unread excess input.
- Valid local and proxy requests after the client half-closes its write side.
- Exact binary Content-Length/chunked uploads, valid quoted chunk extensions and
  opaque trailer bytes.
- Proxy HEAD lengths, absent HEAD bodies on chunked upstreams, and following GET.
- Ambiguous, duplicate, missing and invalid upstream framing; exact GET versus
  POST retry counts; unusual forwarded status; interim 100 response.
- Invalid chunks, folded/invalid trailers, empty extension names, missing
  extension values and unterminated quoted extensions.
- Empty cache entries are reused and then evicted under the entry cap; large
  response-header metadata is reused and then evicted under the metadata cap.
  A 60-second TTL prevents expiry from explaining those evictions.
- With 96 proxy clients held in flight, exactly 64 upstream exchanges begin.
  An ordinary local request still completes. Sixteen queued clients are reset;
  the remaining 80 receive exact bodies and the cancelled requests are not
  forwarded upstream.

`focused-005/stdout.json` records 30 additional cycles of upstream idle expiry,
descriptor reuse and Host-versus-actual-upstream authority checks on the final
candidate. The same focused probe also passed against the earlier api-005 source
in `focused-004/`; it did not reproduce the descriptor ABA edge found by code
review. The final pool checks explicitly prevent stale descriptor generations
and mismatched authorities from being selected.

After the current-source full-matrix timeout, `focused-007/` and `focused-008/`
ran bounded functional state-transition regressions against the unchanged
api-006 candidate on CPUs 8,23. Both passed. These cover 160 persistent clients
through cache hits, 4/64 KiB misses, truncated upstream retries and recovery;
16 active and 16 queued cancellations among 160 held requests; and 96 queued
requests through final upstream timeouts followed by new successful service.
`focused-008/stdout.json` additionally records four final waves of 160 persistent
64 KiB misses. Every completed client closes immediately without issuing another
request, while remaining clients are still queued. All 640 exact responses and
a subsequent cold proxy probe succeeded. No performance traffic was launched
for these fixed functional cases. These probes did not reproduce the central
4096-client timeout or establish its cause.

## Performance status and limits

The builder did not start competing benchmarks. The coordinating agent ran the
supplemental native v2 matrix at
`.runs/references/supplemental-batch-v2-001/stage-05-cpp/result.json`, using the
api-004 source hash. That result contains all 24 workloads, one round each, with
one second warmup and three seconds measurement. It is explicitly noncanonical
and not comparable to the official asyncio measurement suite. The final source
identity in that result matches api-004, not the repaired api-006 source.

Five workloads had non-200 status failures: proxy 4/64 KiB at 4096 clients,
cache-miss 4 KiB at 256 clients, and cache-miss 4/64 KiB at 4096 clients. The
respective counts were 7226, 3858, 246, 4856 and 3545, with zero client timeouts.
Both 4096-client proxy cases and the 64 KiB/4096-client cache-miss case had
unsaturated generators and upstreams. Their failure therefore cannot be dismissed
as generator saturation. The one-round matrix was ineligible overall.

The likely connection-burst failure mechanism was inferred from unrestricted
upstream admission and the small accept backlog of the trusted asyncio upstream;
packet-level errors were not recorded, so that diagnosis is not proven by the
status-only worker results. The FIFO limit prevents that burst and is separately
validated by the held-request focused probe. No speedup or complete performance
acceptance is claimed.

The baseline table below retains successful-request latency alongside failures.
One round supplies no estimate of round spread; its min/median/max throughput
values coincide. CPU columns are measurement-window seconds. RSS is sampled
server peak KiB, excluding generator RSS. Eligibility incorporates the native
diagnostic's recorded generator and upstream saturation checks.

| Baseline workload | RPS | p50 ms | p95 ms | p99 ms | Failures | Timeouts | Server CPU s | RSS KiB | Upstream CPU s | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| fresh-4096-256 | 18004.0 | 11.1 | 26.8 | 36.3 | 0 | 0 | 2.25 | 4440 | 0.00 | yes |
| fresh-65536-256 | 22739.3 | 10.8 | 14.1 | 25.5 | 0 | 0 | 2.85 | 4448 | 0.00 | no |
| persistent-4096-256 | 47668.0 | 4.4 | 11.0 | 13.3 | 0 | 0 | 2.61 | 4448 | 0.00 | yes |
| persistent-65536-256 | 37530.7 | 5.2 | 13.2 | 20.7 | 0 | 0 | 2.45 | 4448 | 0.00 | yes |
| fresh-4096-4096 | 22766.3 | 169.2 | 188.5 | 192.4 | 0 | 0 | 2.91 | 5364 | 0.00 | yes |
| fresh-65536-4096 | 15764.3 | 218.0 | 383.5 | 395.2 | 0 | 0 | 2.28 | 5920 | 0.00 | no |
| persistent-4096-4096 | 31189.3 | 91.2 | 188.4 | 248.0 | 0 | 0 | 2.01 | 6252 | 0.00 | yes |
| persistent-65536-4096 | 41326.3 | 93.1 | 117.0 | 131.1 | 0 | 0 | 2.88 | 6252 | 0.00 | no |
| routed-4096-256 | 47402.3 | 4.1 | 11.0 | 17.6 | 0 | 0 | 2.38 | 6252 | 0.00 | yes |
| routed-65536-256 | 51150.3 | 4.5 | 9.1 | 12.6 | 0 | 0 | 2.87 | 6048 | 0.00 | no |
| routed-4096-4096 | 52734.0 | 72.2 | 95.5 | 148.2 | 0 | 0 | 2.83 | 6252 | 0.00 | yes |
| routed-65536-4096 | 41243.7 | 91.0 | 112.9 | 215.0 | 0 | 0 | 2.77 | 6252 | 0.00 | yes |
| proxy-4096-256 | 14070.7 | 15.0 | 35.0 | 49.6 | 0 | 0 | 1.77 | 6252 | 1.68 | yes |
| proxy-65536-256 | 5783.7 | 43.7 | 77.0 | 106.5 | 0 | 0 | 1.77 | 9304 | 1.56 | yes |
| proxy-4096-4096 | 3447.7 | 210.1 | 819.8 | 872.0 | 7226 | 0 | 1.45 | 15732 | 0.80 | no |
| proxy-65536-4096 | 4564.0 | 269.2 | 1001.1 | 1146.7 | 3858 | 0 | 2.24 | 25752 | 1.62 | no |
| cache-hit-4096-256 | 60033.3 | 4.0 | 7.1 | 10.0 | 0 | 0 | 2.94 | 25752 | 0.02 | yes |
| cache-hit-65536-256 | 39885.7 | 6.1 | 10.6 | 14.4 | 0 | 0 | 2.97 | 25752 | 0.01 | yes |
| cache-miss-4096-256 | 9569.3 | 11.1 | 32.7 | 178.9 | 246 | 0 | 1.28 | 14880 | 1.28 | no |
| cache-miss-65536-256 | 9633.0 | 23.9 | 36.0 | 69.3 | 0 | 0 | 2.67 | 14880 | 2.19 | yes |
| cache-hit-4096-4096 | 56291.7 | 69.4 | 82.2 | 116.8 | 0 | 0 | 2.92 | 14880 | 0.00 | no |
| cache-hit-65536-4096 | 34462.0 | 112.7 | 140.7 | 150.0 | 0 | 0 | 2.94 | 14880 | 0.00 | no |
| cache-miss-4096-4096 | 10845.7 | 90.7 | 645.1 | 739.8 | 4856 | 0 | 2.58 | 14880 | 1.72 | no |
| cache-miss-65536-4096 | 5942.3 | 238.3 | 819.1 | 963.8 | 3545 | 0 | 2.63 | 25628 | 1.97 | no |

Neither architectural choices nor passing these finite API/focused suites prove
all possible contract behavior, peak-memory safety for every configuration and
client pattern, or maximum performance.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 17/24 rounds were eligible;
measurement failures: 4037; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-05-cpp/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.

## Current-source complete diagnostic

The coordinated result at
`.runs/references/supplemental-batch-v2-cpp-final-001/stage-05-cpp/result.json`
records all 24 workloads against the final api-006 source hash, one round each.
Every proxy workload is eligible with zero measured or warmup failures. The first
23 workloads all have zero measured and warmup failures. Other individual rows
remain ineligible where generator CPU/lag validity checks failed.

The final cache-miss-65536-4096 row has 12846 measured attempts: 8809 successful
responses and 4037 client timeouts. Of the 4096 final outstanding requests, 59
complete after the measurement window and 4037 time out during worker drain.
Warmup failures are zero. The generator and upstream saturation flags are false.
The server used 1.00 CPU second and the upstream 0.86 CPU second during a sampled
2.997-second measurement window; averages do not prove uninterrupted dispatch.
There is no server or upstream scheduling-lag telemetry in that result.

Code review found no admitted-slot leak: slots release before persistent-client
EOF handling or final-close drain, and cancellation releases the slot before
pumping the FIFO. The explicit final-wave close regression above also passes.
These facts do not explain the 4096-client failure. A server/upstream scheduling
pause and a workload-dependent server defect remain possibilities; neither is
established. Source is unchanged after this investigation. Overall eligibility
is false, and stability or a complete performance pass is not claimed.

One round provides no round-spread estimate. The same latency, CPU and RSS units
as the preceding baseline table apply.

| Current workload | RPS | p50 ms | p95 ms | p99 ms | Failures | Timeouts | Server CPU s | RSS KiB | Upstream CPU s | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| fresh-4096-256 | 25135.0 | 10.0 | 12.1 | 14.4 | 0 | 0 | 2.98 | 4444 | 0.00 | no |
| fresh-65536-256 | 22307.7 | 11.0 | 14.9 | 25.4 | 0 | 0 | 2.86 | 4444 | 0.00 | no |
| persistent-4096-256 | 49634.7 | 5.0 | 8.7 | 11.0 | 0 | 0 | 2.99 | 4444 | 0.00 | yes |
| persistent-65536-256 | 42802.3 | 5.8 | 10.0 | 12.2 | 0 | 0 | 2.96 | 4444 | 0.00 | yes |
| fresh-4096-4096 | 21558.3 | 173.1 | 209.5 | 216.5 | 0 | 0 | 2.84 | 6432 | 0.00 | no |
| fresh-65536-4096 | 19715.3 | 186.5 | 222.3 | 1455.4 | 0 | 0 | 2.93 | 5408 | 0.00 | no |
| persistent-4096-4096 | 43387.0 | 91.1 | 106.0 | 117.0 | 0 | 0 | 2.95 | 6304 | 0.00 | yes |
| persistent-65536-4096 | 36786.3 | 102.0 | 148.2 | 149.7 | 0 | 0 | 2.82 | 6304 | 0.00 | yes |
| routed-4096-256 | 46503.7 | 4.9 | 9.4 | 20.0 | 0 | 0 | 2.74 | 6304 | 0.00 | yes |
| routed-65536-256 | 41798.7 | 5.2 | 10.1 | 19.2 | 0 | 0 | 2.72 | 5408 | 0.00 | yes |
| routed-4096-4096 | 47774.7 | 81.1 | 100.4 | 120.1 | 0 | 0 | 2.85 | 6304 | 0.00 | yes |
| routed-65536-4096 | 42716.0 | 93.9 | 98.3 | 100.0 | 0 | 0 | 2.97 | 6304 | 0.00 | yes |
| proxy-4096-256 | 31029.0 | 8.0 | 13.1 | 18.0 | 0 | 0 | 2.54 | 6320 | 2.20 | yes |
| proxy-65536-256 | 15483.3 | 15.1 | 24.1 | 30.0 | 0 | 0 | 2.82 | 5904 | 2.42 | yes |
| proxy-4096-4096 | 19486.7 | 186.0 | 320.0 | 327.0 | 0 | 0 | 2.30 | 8460 | 1.53 | yes |
| proxy-65536-4096 | 10867.3 | 334.1 | 424.2 | 435.0 | 0 | 0 | 2.75 | 8596 | 2.13 | yes |
| cache-hit-4096-256 | 74177.7 | 3.1 | 6.0 | 7.2 | 0 | 0 | 2.97 | 8596 | 0.00 | yes |
| cache-hit-65536-256 | 39803.7 | 6.0 | 10.9 | 16.4 | 0 | 0 | 3.00 | 8504 | 0.00 | no |
| cache-miss-4096-256 | 33089.7 | 7.1 | 12.1 | 19.3 | 0 | 0 | 2.53 | 8480 | 2.04 | yes |
| cache-miss-65536-256 | 13578.0 | 17.0 | 30.1 | 39.0 | 0 | 0 | 2.54 | 8480 | 2.33 | yes |
| cache-hit-4096-4096 | 62203.3 | 63.9 | 72.7 | 103.3 | 0 | 0 | 2.89 | 8480 | 0.00 | yes |
| cache-hit-65536-4096 | 41778.7 | 91.1 | 129.0 | 154.7 | 0 | 0 | 2.94 | 8480 | 0.00 | no |
| cache-miss-4096-4096 | 28382.0 | 135.1 | 185.1 | 198.1 | 0 | 0 | 2.75 | 8480 | 1.99 | yes |
| cache-miss-65536-4096 | 2916.7 | 391.7 | 1235.7 | 1629.1 | 4037 | 4037 | 1.00 | 8788 | 0.86 | no |
