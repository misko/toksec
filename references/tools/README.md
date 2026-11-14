# Supplemental native load diagnostic

This host-only tool investigates the asyncio generator bottleneck recorded in
`diagnostics/calibration/http-v8`. It does not modify or replace the frozen
contract, evaluator, canonical full-suite metrics, or promotion comparison. Its
results are labeled **supplemental and not comparable to official metrics**.
An eligible supplemental round does not make an ineligible official round valid.

Version 2 uses schema `toksec-supplemental-native-v2`. **All version 1 eligibility
claims are provisional**, including the earlier Stage 1 C++ 80,246 req/s round.
The v1 monitor could discard a long scheduling pause that resumed after the
measurement window ended. Raw v1 records remain preserved for audit; use v2
reruns for eligibility claims. The change does not affect the official harness.

The current orchestration adds guard revision `v2-upstream-liveness-1`, recorded
as `guard_revision` in future results. It polls the trusted upstream process
before, during, and after rounds, so an exited unreaped child cannot pass a
`/proc/PID` existence check. Future proxy runs retain `upstream.stdout.log` and
`upstream.stderr.log`. Numeric metrics, workload timings, latency bins, and
eligibility thresholds are unchanged.

Completed v2 measurements used orchestration SHA-256
`4aeb4b44a346d55dac6c6e6cf44ef653f69d318e846cad9e1a0ddd5efa3066e0`,
preserved exactly at `.runs/references/tool-snapshot-v2/supplemental.py` and in
commit `d430936`. Those raw records remain frozen. The old guard could miss an
exited fixture, but no past timeout or status failure is attributed to that
defect without evidence; later recovery with the same fixture PID excludes a
permanent fixture exit for the reviewed intermittent cases. This guard revision
has unit validation only; it has not run load traffic.

`native_load.cpp` is a Linux C++17 epoll worker. Four independently pinned
processes run 64 or 1024 clients each, with exactly one request outstanding per
client. All declared plaintext workloads are supported: fresh or persistent,
4/64 KiB, routed hosts, proxy, cache hit, and cache miss. The existing workload
matrix supplies paths and headers; TLS/gzip and changed timing are rejected.
Each round starts synchronously, warms up for one second, measures for three,
and applies a two-second whole-request deadline. Fresh latency includes connect;
persistent latency includes reconnects. Failures remain in the counters.

The incremental validator requires HTTP/1.0 or HTTP/1.1 status 200, a single
decimal Content-Length equal to the expected size, no Transfer-Encoding, and
exact payload bytes. It rejects malformed headers, truncated/incorrect bodies,
and unsolicited bytes received or already queued beyond the message boundary.
As with any persistent Content-Length protocol, an arbitrarily delayed extra
byte is detected when subsequently read, rather than by waiting for EOF after
every response. Response body bytes are compared with `memcmp` and never kept
per connection. A `Connection: close` token triggers reconnecting.

The Python launcher uses unchanged `sandbox.running`, resolves the actual
candidate PID, and enters only its network/user namespaces using the evaluator's
existing nsenter pattern. The candidate remains sandboxed. Stages 4/5 reuse the
unchanged `evaluation.smoke.upstream` fixture pinned to a sixth CPU. Stage 5
uses the canonical benchmark cache configuration. No model calls occur.

Before `measure`, the tool requires an evaluator `result.json` with every
required full API case successful exactly once, successful build, the current
framework fingerprint and matching source SHA-256. The artifact is taken from
that result's `candidate/`, whose saved source must match too. Candidate binary,
worker, and orchestration hashes are recorded; identities are checked again
afterward. Keep the accepted artifact immutable throughout the campaign.

Run correctness tests without traffic:

```sh
taskset -c 22 python3 -m unittest discover -s references/tools -p 'test_*.py' -v
```

Coordinate CPU scheduling before **any** performance run. `--cpus` requires the
server first, followed by four generators, then the upstream for stages 4/5.
The server CPU must have the lowest numeric ID because `sandbox.running` uses
that rule. The launcher shares `.runs/references/validation.lock` with the
official serial reference validator. This prevents overlap between these
launchers, but cannot reserve cores against unrelated host jobs. Host load and
event-loop lag are recorded; taskset alone does not prove idle cores.

```sh
# Static probe is intentionally not required to pass the stage API. Its results
# certify neither a conforming server nor proxy/upstream headroom.
python3 references/tools/supplemental.py calibrate \
  --cpus 10,11,12,13,14 --rounds 1 \
  --workload fresh-4096-256 --workload fresh-4096-4096 \
  --output .runs/references/supplemental-static-001

python3 references/tools/supplemental.py measure \
  --acceptance .runs/references/stage-01-cpp/performance-001/result.json \
  --source references/stage-01/cpp/main.cpp \
  --cpus 10,11,12,13,14 --rounds 5 \
  --output .runs/references/supplemental-stage01-cpp-001
```

Omit `--workload` for the complete declared matrix; repeat it to select a
diagnostic subset. The default is five rounds, with one through five supported.
Five rounds report median/min/max throughput and worst p99. The raw worker
JSON includes 20,002 latency bins of 0.1 ms (last bin overflows), exact failures,
timeouts, successful requests started in measurement, completions within the
window, payload bytes, CPU, peak RSS, and lag. Aggregate JSON retains those bins
and per-worker details. The directory also retains server/driver logs,
measurement/partial JSON, the native binary, build identity, and command inputs.
Exit 0 means all selected supplemental rounds are eligible; exit 2 means one
or more are inconclusive; other failures raise an error and retain partial data.

Eligibility is conservative: both whole-round and measurement-window generator
CPU above 90% invalidate a round; event-loop lag over 20 ms in more than
max(1, 1% of samples) does too. V2 schedules exactly 300 measurement deadlines
at a fixed 10 ms cadence. Every deadline is accounted for, including deadlines
observed after measurement ends; missing coverage invalidates the round.
`lag_missed_deadlines` counts deadlines delayed by more than one 10 ms tick;
`lag_over_20ms` applies the eligibility threshold. The original drifting v1
interior-sampling gate is retained as an additional requirement under
`legacy_lag_*`, so the denominator change cannot relax its decision.
Missing lag/CPU samples, upstream CPU above 90%,
server children, missing clients, inconsistent accounting, any warmup or
measurement failure, or no useful measured work also invalidate the round.
Upstream CPU sampling covers at least 2.8 seconds of the measurement window.
The same generator/upstream thresholds as the official suite are preserved;
additional checks only make this diagnostic stricter. CPU/RSS are process-level;
kernel networking and unrelated host processes are not attributed as server CPU.

The parser/gate tests exercise fragmentation, both calibration payload sizes,
bad status, duplicate/ambiguous framing, missing/invalid lengths, encoding,
malformed/oversize headers, corrupt/truncated/trailing payload, stale/subset API
evidence, and saturation/accounting rejection. A real static calibration is
still required after changes to the worker. Proxy readiness requires separate
accepted proxy measurements and is never inferred from static calibration.
Deterministic native-monitor tests cover ordinary sampling, a multi-second pause
resuming after measurement ends, a shorter end-crossing pause without request
timeouts, incomplete coverage, and pauses outside the measurement window.

Run the real socket failure-accounting test only during an authorized CPU slot:

```sh
python3 references/tools/check_worker_faults.py \
  --server-cpu 10 --worker-cpu 11 \
  --worker .runs/references/supplemental-static-001/native_load \
  --output .runs/references/supplemental-worker-faults-001.json
```

It uses a local mock server, the actual native worker, the unchanged 1+3+2
timing, and the campaign lock. It checks reconnecting valid traffic and four
faults: bad status, duplicate length, corrupt payload, and truncation. Faulty
responses must produce zero successful responses and explicit failed attempts.
These deliberate-fault results are correctness evidence with no throughput claim.
