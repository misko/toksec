# Stage 4 C++ reference

The implementation is in `main.cpp`. It was written from scratch using the C++
standard library and Linux/POSIX APIs. No earlier experimental implementation,
third-party dependency, subprocess delegation, or paid model call was used.

Final source SHA-256:
`f6e95b7a1d1dac3ba48dd093cada8eca52fa0a0426e3ff58f432e6457f0c4ab3`.

Status: implemented and validated by all 31 applicable host API checks. Central
supplemental measurements of the final source still show intermittent failures
at 4096 clients, including 5427 timeouts in the repeated 4 KiB proxy diagnostic.
The cause remains unresolved. The finite functional and API checks below passed,
but they do not establish repeated high-client stability. This reference has no
production or performance certification claim. The builder ran correctness
probes only; performance measurements were coordinated centrally.

The server uses one nonblocking epoll loop for downstream and upstream sockets.
It processes one request at a time per downstream connection, retaining order and
applying backpressure while a response is pending. This is a conservative pipeline
policy within every positive configured pipeline depth. Header, upload, idle,
upstream, and stalled-write handling use monotonic deadlines. Generation IDs
protect descriptor reuse; timer and waiting-request queues periodically discard
retired entries.

Local routing validates the Host, performs strict one-pass UTF-8 path decoding,
and walks path components through directory descriptors with `openat` and
`O_NOFOLLOW`. `O_NONBLOCK` avoids blocking on a FIFO before its file type is
rejected. Responses use `sendfile` with per-response offsets and shared immutable
file metadata. The cache holds at most 512 entries; files still being transmitted
can outlive cache eviction. Indexes, redirects, aliases, MIME types, stable ETags,
conditional precedence, ranges, and HEAD are handled after route selection.

The proxy preserves the escaped origin target and query after prefix removal.
It decodes request and response chunk framing, bounds decoded bodies, removes
trailers, validates ambiguous framing, and strips both fixed hop-by-hop headers
and Connection-nominated fields. Healthy upstream connections are pooled by
authority. Consecutive initial selections use round robin; GET and HEAD can retry
once at the next upstream before a response starts, while POST is never retried.
Informational upstream responses can precede the final response in the same read.

At most 64 proxy operations hold complete request/response buffers at once. The
operation slot remains occupied until the downstream response is fully written,
so 4096 stalled clients cannot each accumulate a complete proxy response. Waiting
clients hold bounded request-header/input storage. Completed upstream body strings
move into the downstream response, and upstream request buffers larger than
64 KiB release their allocation after transmission. The upstream socket map is
trimmed before growth beyond 256 entries. These are implementation bounds, not a
measured peak-RSS result. Per-operation body storage still depends on configured
`body_bytes`; arbitrarily large configured bodies were not stress-tested.

Half-closed clients can finish their response. Normal intentional closes send a
write-side FIN and briefly drain extra input, avoiding a TCP reset that could
discard the final response when excess pipelined requests remain. Malformed input,
transport errors, and deadline expiry cannot terminate the event loop. C++ owns
the buffers and socket records; explicit POSIX calls manage sockets, epoll,
directory/file descriptors, `sendfile`, and shutdown. No external FFI library or
runtime loading is used.

API evidence is retained under `.runs/references/stage-04-cpp`:

| Run | Source SHA-256 | Result |
| --- | --- | --- |
| `api-001/result.json` | `47e945bdd3b277d1b70645b1d880495c8012d76ad975578a40f13c104492176d` | 31/31 passed |
| `api-002/result.json` | `41480801fe12eb9c56f1531b916ebf4a47658ceaba4f6d7fbda38f195674a72f` | 31/31 passed |
| `api-003/result.json` | `66b3d15573da7aaec51ff4eca3067ca429cc08b8e231dd3ca6433919fab5eed0` | 31/31 passed, prior source |
| `api-004/result.json` | `ac8dbd1258419ca6b7b1a4e9635b65946713c848d58d95b06b844a39185ca36b` | 31/31 passed, pool generation fix |
| `api-005/result.json` | `f6e95b7a1d1dac3ba48dd093cada8eca52fa0a0426e3ff58f432e6457f0c4ab3` | 31/31 passed, final source |

Each API run used the required command with `--section api --level 4 --language
cpp`, this reference source, and a new output directory. API evaluation was
pinned with `taskset -c 6,22`, allowing the API driver its separate upstream CPU;
standalone development compilation used CPU 6. The final evaluator compilation
completed in 4.000 seconds with empty diagnostics using g++ 15.2.0. An additional
`-Wall -Wextra -Wpedantic -fsyntax-only` review produced no diagnostics after source
formatting. The final waiter-queue compaction was subsequently covered by the
final normal evaluator build and API run.

The retained diagnostic program is
`.runs/references/stage-04-cpp/focused.py` (SHA-256
`56f95e21363a638a29b778a68cc2f95c032d254cbf4bcaf710d9c32bf299367f`).
Its successful output is `focused-result.json`. It ran against the `api-002`
implementation, before the final formatting and retired-waiter compaction, and
checked 11 additional groups:

- A half-close preserves an exact 8 MiB binary response.
- A three-response request limit closes cleanly with 4997 excess pipelined requests.
- Escaped proxy paths and queries survive prefix removal.
- A coalesced upstream 103 and 200 yields the final response correctly.
- HEAD preserves a representation length larger than the configured body limit.
- Upstream chunk extension syntax, quoted values, and bounded trailers are validated.
- Request chunk extensions are validated and trailers are removed.
- An empty Range field returns 400.
- A failed GET makes two upstream attempts and a failed POST makes one.
- Connection-nominated fields are removed in both directions.
- A stalled 8 MiB local response permits prompt ordinary-client service.

All these checks passed. The original working checkpoint is retained as
`.runs/references/stage-04-cpp/checkpoint-api-001.cpp`. No API failures were
discarded, and no harness, contract, or accepted-result file was modified.

The finite API and focused suites do not establish exhaustive conformance or
maximum performance. The declared 16-workload matrix, both client counts,
p50/p95/p99, error/timeouts, round spread, CPU/RSS, generator lag, upstream
utilization, and eligibility remain to be recorded by the coordinating agent.


The coordinating agent's prior-source diagnostic is retained at
`.runs/references/supplemental-batch-v2-001/stage-04-cpp/result.json`.
It completed all 16 workloads, with one supplemental round per workload. It is
not the canonical five-round performance matrix. In the first proxy workload,
`proxy-4096-256`, it recorded zero measured valid requests per second, 298 measured
timeouts, and 256 warmup failures. Server measurement-window utilization was
0.669%, upstream utilization was 0%, and neither generator nor upstream was marked
saturated. The following 64 KiB/256-client proxy round recorded 9717.7 valid RPS
without measured or warmup failures, and 4 KiB/4096-client proxy recorded 29951
valid RPS without measured or warmup failures. The final 64 KiB/4096-client proxy
round had 1868 warmup failures. Failed and ineligible observations remain evidence.
These numbers describe the prior source only.

Review found a distinct concrete upstream-pool defect: an idle entry stored only
an fd, so expiry followed by Linux fd reuse could make an old authority's entry
select an idle socket now connected to a different authority. The fix stores the
registration generation and checks both generation and authority at checkout.
The functional regression forces real descriptor reuse: the old source sends an
authority-0 request over authority 1's reused socket (expected reproducer exit 2),
while the corrected source opens/selects the authority-0 socket and leaves the
other pool untouched (exit 0). The regression ran on CPU 6 without performance
traffic. Its retained files are:

- `pool-regression-before.cpp`, including `checkpoint-api-003.cpp`;
- `pool-regression-after.cpp`, including the corrected source;
- `pool-regression-body.h`, SHA-256 `803163f72979f7a26e099e2c4fc28b6b41562f32eccaf82e9e0703a430758336`;
- `pool-regression-result.json`, recording both actual exits and outputs.

All regression paths are under `.runs/references/stage-04-cpp`. The subsequent
full sandbox API run `api-004` passed all 31 checks on CPUs 6 and 22. No performance
traffic was generated during this investigation.

The pool defect does not establish the cause of the first-proxy stall: the
preceding 12 workloads were local-file traffic and should not populate the
upstream pool. Review found no static-route mutation of the proxy operation count
and no confirmed imbalance in admission, completion, timeout, or disconnect slot
release. The retained generator combines connect-phase and response-phase expiry
under `timeout`, so the data cannot distinguish server/proxy state from TCP
connection-establishment carryover. No phase trace or epoll-control error trace
was retained. A cold proxy run versus the same sequenced run is the next planned
central diagnostic. The unexplained stall remains an unresolved limitation;
performance validation of this corrected source is pending.


A later central run of the pool-corrected `api-004` source completed the full
16-workload supplemental matrix with zero measured and warmup failures:
`.runs/references/supplemental-v2-stage04-cpp-fixed-001/result.json`.
That clean single round did not establish stability. The subsequent five-round
proxy-only check,
`.runs/references/supplemental-v2-stage04-cpp-proxy-5rounds-001/result.json`,
showed intermittent failures at 4096 clients without generator or upstream
saturation. The 4 KiB/4096-client second round recorded 2960 failures (2946
timeouts); the 64 KiB/4096-client third, fourth, and fifth rounds recorded 232,
1190, and 1152 timeouts, respectively, with 1850 and 2216 warmup failures in the
third and fifth rounds. These observations remain unresolved performance evidence
for that prior source, despite its API acceptance and clean intervening matrix.

Investigation confirmed a separate admission fairness defect. A free proxy slot
could be granted to a newly readable request while older requests were queued.
If a response completed earlier in the same epoll batch, follow-up requests could
repeatedly take that slot before the next `wakewaiters()` call. The final fix
makes new requests join the existing queue whenever it is nonempty. A bounded
state-transition regression using real socketpairs reproduces 16 consecutive
bypasses with the `api-004` source. With the final source, the oldest request
advances first, a successor advances when its slot is released, and a canceled
queued generation is ignored after its fd is reused. It does not generate a load
benchmark or reproduce the measured network timeouts themselves.

The retained regression files are `admission-regression-before.cpp`,
`admission-regression-after.cpp`, `admission-regression-body.h` (SHA-256
`42d917b4ea197c4c081c52d7549cf3c6ff2cfa2b8e416f7e117699c586dd4441`),
and `admission-regression-result.json`, under `.runs/references/stage-04-cpp`.
The prior source is retained as `checkpoint-api-004.cpp`. The actual before/after
regression exits were 2 (confirmed bypass) and 0 (FIFO progress and canceled-entry
checks passed). Both ran on CPU 6. The final full sandbox API run `api-005`
subsequently passed 31/31 on CPUs 6 and 22 with empty compiler diagnostics.

The fairness regression establishes a concrete starvation path, but it does not
establish that path as the cause of every observed timeout. No performance
traffic was run by this builder during either investigation. The final source is
frozen for coordinated remeasurement; repeated high-client performance stability
is not established.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 14/16 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-04-cpp/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.


The repeated proxy check of the final fairness-corrected source is retained at
`.runs/references/supplemental-v2-stage04-cpp-proxy-final-5rounds-001/partial.json`
(and its completed result when available). The 4 KiB/4096-client third and fourth
rounds recorded 1740 and 3687 timeouts, totaling 5427; the other three 4 KiB rounds
had no measured failures. The 256-client rounds and the observed five 64 KiB/4096
rounds had no measured failures. In the fourth failing 4 KiB round, server CPU
utilization averaged 27.1% and upstream utilization averaged 19.0%. Such averages
and healthy generator lag do not prove continuous availability of the separate
server and upstream CPUs. Host contention remains a possible confound, not an
established explanation. The two repaired source defects therefore did not
establish the cause or resolve the observed repeated stress failures.

A final finite functional probe used the unchanged final source, server CPU 6,
and driver/upstream CPU 22. It ran eight bursts of 129, 257, 513, and 1025 clients,
twice, with 4 KiB/64 KiB exact payloads, two sequential requests per ordinary
connection, half-close EOF checks, deliberate FIN/RST cancellations, and subsequent
recovery bursts. With the driver's descriptor limit raised to 16384 and the
contract's default two-second idle/write limits, all 3461 ordinary connections
completed both exact responses, 192 FIN and 195 RST cancellations were intentional,
and there were no unexpected errors. This tests bounded cancellation and recovery;
it is not the 4096-client measurement and does not reproduce or explain its stall.
No throughput or latency score was produced.

Probe evidence under `.runs/references/stage-04-cpp` is retained as follows:

- `burst-functional-result-001.json`: 148 connect-phase EMFILE failures from the
  probe driver's original 1024-descriptor soft limit; this attempt is inconclusive
  for candidate correctness.
- `burst-functional-result-002.json`: 16 send/header closure observations with
  a deliberately short 300 ms server idle limit and the corrected descriptor
  limit. Their cause was not established; they did not recur with default limits.
- `burst-functional-result-003.json`: all eight bursts passed with default
  idle/write limits, descriptor limit 16384, and mixed FIN/RST cancellation.
- `burst-functional-001.py` and `burst-functional-002.py` preserve the earlier
  probe versions. Final `burst-functional.py` has SHA-256
  `f99cb69f2d381f6f8f7cfb4f2b978de033ff3a1f9f8213d85155145c2209d7c1`.

No additional server edit followed `api-005`; its source hash and API acceptance
remain current. Further counter, timer, queue, and mass-close review did not
identify another confirmed implementation defect. The repeated 4096-client
failures are archived as unresolved rather than marked stable or eligible.
