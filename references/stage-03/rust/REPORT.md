# Stage 3 Rust reference

Implemented from scratch as one independently compilable Rust 2021 source file.
The final source is `references/stage-03/rust/main.rs`.

Current status: implemented and API-validated. A coordinator-run supplemental
native matrix exposed admission failures in the prior source. The listener backlog
was corrected and revalidated; performance on the revised source awaits a
coordinated rerun. No post-fix performance claim is made.

## Architecture and resource bounds

A single Linux epoll event loop owns nonblocking TCP connections. One parsed
request and one response are active per connection; the input byte buffer is
bounded by configured `header_bytes`. Parsing and sending advance in order, with
read interest paused while output is blocked. Buffered pipelines resume through
writable readiness even when no new socket bytes arrive. Each event has a 1 MiB
transfer budget and at most `min(pipeline_depth, 32)` completed responses, limiting
one client's work before other ready connections run. The listener backlog is
explicitly set to at least 128 and otherwise to the configured connection capacity,
subject to the kernel cap; the accept loop still admits at most 128 sockets per
listener event so existing connections receive service between accept batches.

The immutable-file cache holds at most 256 representations. Files up to 128 KiB
can use shared in-memory bodies, with a 16 MiB aggregate live-byte budget that
also counts entries retained by responses after cache eviction. Larger files and
files that exceed that budget retain a descriptor and use sendfile. Headers and
small cached bodies use writev. Avoiding redundant epoll_ctl calls reduces the
ordinary completed-request path's system calls; no speedup is asserted without
measurement.

Path resolution walks relative to the chosen root directory descriptor using
openat with O_NOFOLLOW, O_NONBLOCK and O_CLOEXEC. Each intermediate object must be
a directory, and the representation must be regular. Directory indexes use the
same walk. Host, alias and index selection precede metadata-derived quoted ETag,
conditional and range handling. The files are immutable as required by the
contract; the cache deliberately does not watch for external modifications.

Header deadlines begin at the first received byte and are absolute. Idle and
write-progress timers are separate. Deadline sweeps occur approximately every
25 ms. Connection limits and request counts use the supplied configuration.
After a final response, the server shuts down its write side and asynchronously
drains surplus request bytes, avoiding an immediate TCP reset that could discard
the final response. This drain lasts at most 250 ms or the shorter configured
idle timeout.

## Unsafe and FFI use

The implementation declares direct libc/Linux FFI for listen, epoll_create1, epoll_ctl,
epoll_wait, read, writev, sendfile and openat. Unsafe operations are confined to
those calls, constructing owned File handles from successful descriptor returns,
and pointing writev into live owned buffers. The packed epoll_event layout and
numeric Linux flags target the evaluator's Linux ABI. There are no third-party
libraries, subprocess servers, downloads, runtime symbol lookup or model calls.

## Full API evidence

All commands were launched from the repository root with `taskset -c 5` so both
compilation and the API evaluation used CPU 5. Each output directory is unique;
none of the earlier result records were edited.

| Run | Source SHA-256 | Result |
|---|---|---|
| `.runs/references/stage-03-rust/api-001/result.json` | `754993d248fea795c04fe69f1fbd8e07dba67b3a843411ce88b455a29bdf7a8d` | 26/26 API checks passed; two compiler warnings |
| `.runs/references/stage-03-rust/api-002/result.json` | `5c08f61213aa772450dad73b33668aa9e85f44e2a470ecb0f5c320a588d8094c` | 26/26 API checks passed; no compiler diagnostics |
| `.runs/references/stage-03-rust/api-003/result.json` | `c6d1362c4505d3c60bfb97e019f99f835006f4f603d8a0e7917fc8aaa717ab44` | Before backlog correction: 26/26 API checks passed; no compiler diagnostics |
| `.runs/references/stage-03-rust/api-004/result.json` | `d6723a4d91bb9e1329d4bd9277f399666cb200d187d0ee22a45c195385b2faad` | Final source after backlog correction: 26/26 API checks passed; no compiler diagnostics |

Each candidate directory retains the exact compiled source snapshot and build
metadata. The final API command was:

```sh
taskset -c 5 python3 evaluate.py --section api --level 3 --language rust \
  --source references/stage-03/rust/main.rs \
  --output .runs/references/stage-03-rust/api-004
```

The 26 checks include ordinary/binary/large files, strict parsing and framing,
header size and absolute deadline, persistent and pipelined behavior, HEAD,
connection/write limits, slow-client isolation, Host routing, aliases, indexes,
MIME types, ETags, ranges, cross-feature interactions and invalid configuration.
The final server remained running with no diagnostic output at API completion.

## Independent focused tests

`references/stage-03/rust/focused_tests.py` runs independently selected edge tests
against the unchanged evaluator sandbox. Its result is retained at
`.runs/references/stage-03-rust/focused-001/result.json` for the prior source and
`.runs/references/stage-03-rust/focused-002/result.json` for the revised source:
all nine groups passed in both runs.
The tests change host names, alias and redirect paths, max_requests to 3,
pipeline_depth to 1, header_bytes to 256, header timeout to 200 ms, idle timeout
to 250 ms and write timeout to 150 ms. Coverage includes:

- Invalid Host syntax and ports, mixed case, configured alternate host and
  HTTP/1.0 default routing.
- Alias traversal, symlinks, FIFOs, missing index, UTF-8 names, one-pass percent
  decoding and query-preserving directory redirects.
- Empty-file and zero-suffix ranges, clamping, decimal overflow positions,
  malformed/multiple ranges, HEAD lengths and missing-file HEAD framing.
- Conditional lists and weak ETags, with conditional matching before malformed
  ranges on host, alias and index representations.
- Changed exact header-size boundary and non-UTF-8 header values.
- A 3,000-request excess pipeline: all three permitted responses arrive with
  exact payloads, the third advertises close, and the client sees clean EOF.
- A client that half-closes after pipelining a 2 MiB file and a small file:
  both complete representations arrive in order before EOF.
- An independently changed absolute header deadline, plus ordinary-request
  fairness and recovery while a large-file reader stalls.

Reproduce with:

```sh
taskset -c 5 python3 references/stage-03/rust/focused_tests.py \
  .runs/references/stage-03-rust/api-004/candidate \
  .runs/references/stage-03-rust/focused-NEW
```

## Listener correction and diagnostic evidence

The native v2 matrix completed before the source changed; its final result is
`.runs/references/supplemental-batch-v2-001/stage-03-rust/result.json`. Its source
hash is the `api-003` hash. All six 256-client workloads were eligible and had zero
failures; all six 4096-client workloads were ineligible because of timeouts.
These failures are retained and are not described as generator saturation.

Source review found that TcpListener::bind's small default backlog had never been
adjusted to match the configured connection capacity. A no-traffic kernel socket
inspection verified the old backlog was 128, despite max_connections=8192. The
correction explicitly calls libc listen with a backlog derived from the configured
capacity. The host applies its somaxconn=4096 cap. Admission and connection-count
checks otherwise remain unchanged, and the accept-loop fairness bound remains
128 per listener event.

`references/stage-03/rust/listener_backlog_test.py` ran the old and revised API
artifacts inside the unchanged sandbox and inspected `ss -lnt` without request
traffic. Evidence at
`.runs/references/stage-03-rust/listener-backlog-001/result.json` records:

| Source snapshot | Kernel listener backlog |
|---|---:|
| `api-003`, hash `c6d1362c4505d3c60bfb97e019f99f835006f4f603d8a0e7917fc8aaa717ab44` | 128 |
| `api-004`, hash `d6723a4d91bb9e1329d4bd9277f399666cb200d187d0ee22a45c195385b2faad` | 4096 |

The revised source passed the complete 26-check API gate and all nine independent
focused groups on CPU 5. No performance traffic was launched during this fix.
The verified queue limitation is consistent with the observed connection-timeout
pattern; only a coordinated rerun can establish whether it resolves the measured
failures.

## Retained supplemental performance evidence

The following measurements concern the **prior `api-003` source**, not the revised
final source. They are one-round native closed-loop diagnostics run by the
coordinator on CPUs 10–14, with one-second warmup, three-second measurement and
two-second request timeout. They cover the full declared 12-workload matrix but
are explicitly noncanonical and not comparable to the official asyncio metrics.
One round provides no round-spread estimate. All reported latency percentiles
cover successful requests only and must be read alongside failures.

CPU columns show server utilization and summed generator utilization (four
cores permit up to 400%). RSS is server peak RSS. Generator lag is maximum event
loop lag. Every failure in this matrix was a timeout. Exact payload checking and
measurement eligibility are retained in the raw JSON.

| Workload | RPS | Payload MiB/s | p50/p95/p99 ms | Failures/timeouts | CPU server / generators % | Server RSS KiB | Generator lag ms | Eligible |
|---|---:|---:|---|---:|---|---:|---:|---|
| fresh-4096-256 | 39628 | 154.8 | 3.1/5.4/13.7 | 0/0 | 93.1 / 102.6 | 2900 | 15.4 | yes |
| fresh-65536-256 | 23744 | 1484.0 | 7.9/10.2/17.8 | 0/0 | 97.3 / 96.5 | 2908 | 26.3 | yes |
| persistent-4096-256 | 66062 | 258.1 | 3.0/8.9/13.8 | 0/0 | 77.2 / 54.6 | 2908 | 12.3 | yes |
| persistent-65536-256 | 33832 | 2114.5 | 5.9/16.1/30.7 | 0/0 | 80.3 / 68.5 | 2908 | 29.0 | yes |
| fresh-4096-4096 | 17832 | 69.7 | 11.1/1046.2/1458.0 | 2273/2273 | 63.9 / 65.0 | 3980 | 6.8 | no |
| fresh-65536-4096 | 16944 | 1059.0 | 13.4/1080.4/1510.8 | 1459/1459 | 87.2 / 97.2 | 3524 | 24.1 | no |
| persistent-4096-4096 | 73904 | 288.7 | 23.8/32.3/65.3 | 1284/1284 | 99.1 / 72.7 | 5260 | 54.9 | no |
| persistent-65536-4096 | 44293 | 2768.3 | 68.6/83.0/92.9 | 528/528 | 100.1 / 83.8 | 6832 | 12.3 | no |
| routed-4096-256 | 86060 | 336.2 | 3.0/5.1/6.4 | 0/0 | 98.7 / 69.7 | 6712 | 1.5 | yes |
| routed-65536-256 | 44172 | 2760.7 | 5.2/10.0/13.0 | 0/0 | 93.8 / 78.4 | 3600 | 5.2 | yes |
| routed-4096-4096 | 62447 | 243.9 | 46.7/62.2/87.0 | 663/663 | 97.5 / 75.1 | 6752 | 27.4 | no |
| routed-65536-4096 | 36397 | 2274.8 | 43.4/65.7/126.2 | 1812/1812 | 96.4 / 99.4 | 5528 | 67.6 | no |

Final-source performance remains unmeasured. Passing finite API and focused suites
is evidence for their checked behavior, not a proof of complete correctness or
maximum performance. The implementation assumes immutable local representations
and the evaluator's Linux ABI. No unresolved API failure has been observed; the
post-fix 4096-client performance outcome remains unresolved pending measurement.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 10/12 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-03-rust/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
