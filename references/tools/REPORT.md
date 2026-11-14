# Native diagnostic validation

The post-campaign guard revision `v2-upstream-liveness-1` polls the trusted
upstream `Popen` before, during, and after a round, and before final result
publication. It rejects exited children, including unreaped zombies whose
`/proc/PID` entry remains, and retains upstream stdout/stderr in future runs.
Workload timing, numeric aggregation, latency bins, and eligibility thresholds
remain unchanged; the native worker is unchanged. This revision has no load
measurements, and it does not establish the cause of any historical failure.

The exact orchestrator used for completed v2 measurements has SHA-256
`4aeb4b44a346d55dac6c6e6cf44ef653f69d318e846cad9e1a0ddd5efa3066e0`.
It is archived at `.runs/references/tool-snapshot-v2/supplemental.py`, with hash
metadata beside it, and retained in commit `d430936`. All original campaign
records remain untouched. The guard regressions use mocked processes and
network calls, including zero/nonzero exits with a surviving process entry,
exits before/during/after worker execution, a late exit during aggregation, and
fixture log retention. No test sends network traffic.
All 26 tests pass on CPU 22, including an eligible mocked proxy round asserting
unchanged throughput, byte, latency, failure, CPU/RSS, and accounting values.

**All v1 eligibility is provisional because of a lag-coverage defect.** This
includes the historical Stage 1 C++ 80,246 req/s result below. The original raw
records are preserved; their bytes/counters are diagnostic observations, and
their `eligible` or `generator_saturated=false` fields do not certify generator
coverage. Version 2 reruns are required before eligibility is claimed.

The defect was confirmed in the v1 Stage 3 C++ persistent 64 KiB/4096-client
round: one worker reported only 92 lag samples with maximum 19.4 ms, finished
after 5.009 seconds, and timed out all 1024 pending requests. A pending lag
deadline was discarded when dispatch resumed after measurement end. The round
was already ineligible from its 1024 failures, but other v1 rounds could miss a
shorter pause without timing out requests. Existing records lack the timestamp
trace needed to reconstruct complete coverage retrospectively.

V2 schedules 300 fixed measurement deadlines and accounts for delayed deadlines
even when the dispatch resumes after measurement end. It validates exact
coverage and retains the v1 interior-lag gate as an additional requirement,
preventing any threshold relaxation through a denominator change. Deterministic
tests exercise ordinary sampling, end-crossing pauses with and without request
timeouts, missing coverage, and gaps outside measurement. The canonical harness
remains unchanged.

V2 validation passed 17 unit tests, including the actual C++ monitor receiving
deterministic timestamps. A 2.99-second pause resuming after measurement end
accounts for 249 delayed deadlines rather than disappearing. A shorter pause
crossing the end, with no request timeout, is also rejected. All fixed deadlines
are observed on the ordinary timeline; missing final coverage is rejected.

Short v2 static calibration on CPUs 10–14 produced 71,581.0 req/s at 256 clients
and 48,755.7 req/s at 4096 clients for fresh 4 KiB responses, with no failures.
Both are **inconclusive** because of scheduling lag; peaks were 391.6 ms and
1162.5 ms respectively. Every worker accounted for all 300 fixed deadlines.
Evidence: `.runs/references/supplemental-static-v2-001/result.json`.
The five real socket correctness cases were repeated with the v2 worker and
passed. Evidence: `.runs/references/supplemental-worker-faults-v2-001.json`.

The v1 Stage 3 Rust results were reviewed separately: all 8010 measured errors
were timeouts across the six 4096-client workloads; 9061 additional failures
occurred during warmup. There were no classified status, framing, or payload
errors. The records do not identify the timeout phase or retain a scheduling
trace, so they cannot distinguish connection-queue delay, server/generator
scheduling, or an implementation defect. Do not attribute those failures to a
candidate bug without further evidence. V2 reruns provide complete lag coverage.

Implemented a separate supplemental epoll load worker and Python namespace
orchestrator. No frozen contract, harness, evaluator, canonical result, or
reference implementation was changed. The tool supports all declared plaintext
workloads and five-round summaries, full API/source/framework gating, pinned
server/four generators/upstream, exact byte validation, failure accounting,
latency histograms, CPU/RSS, and conservative saturation rejection.

On 2026-11-14, twelve CPU-light tests passed on CPU 22. These include numerous
fragmentation and malformed-response variants as subtests. Real socket tests
on scheduled CPUs 10/11 passed for valid persistent reconnecting traffic and
bad status, duplicate Content-Length, corrupt payload, and truncated payload.
All deliberate faults produced zero successes, positive classified failures,
and exact attempts = successes + failures accounting. Evidence:
`.runs/references/supplemental-worker-faults-001.json`.

One-round static calibration using the unchanged
`evaluation/performance/fixtures/load_reference.cpp` and CPUs 10–14 produced:

| Workload | Supplemental raw req/s | Failures | Eligibility |
|---|---:|---:|---|
| fresh-4096-256 | 50,500.3 | 0 | Inconclusive: generator lag |
| fresh-4096-4096 | 39,963.0 | 0 | Inconclusive: generator lag |

Worker measurement CPU utilization was approximately 26–40%, while host load
was approximately 55.7 on 24 visible CPUs. The 256-client round had three
lag samples over 20 ms in one worker; the 4096-client peak lag was 322.6 ms.
Neither result establishes validated throughput. Evidence:
`.runs/references/supplemental-static-001/result.json`.

The accepted Stage 1 C++ source with SHA-256
`9214aaf0ee5ef0df2c59f6b4d1b73444d72e6737b2ef51c4299ad77900e76336`
then ran one supplemental round for the same two workloads, using its complete
12-case API gate from
`.runs/references/stage-01-cpp/performance-001/result.json`:

| Workload | Supplemental req/s | p50 / p95 / p99 ms | Errors | Eligibility |
|---|---:|---|---:|---|
| fresh-4096-256 | 80,246.0 | 2.8 / 6.1 / 10.2 | 0 | V1 eligibility provisional |
| fresh-4096-4096 | 59,531.7 | 61.7 / 81.2 / 434.1 | 0 | Inconclusive: generator lag |

Evidence: `.runs/references/supplemental-stage01-cpp-001/result.json`.
The 4096-client peak lag was 346.7 ms. These are single-round, selected-workload
diagnostics, not a five-round performance comparison or an official score.
Official full-suite metrics remain canonical and are not comparable to this
different load implementation.

Static calibration did not establish generator readiness across all eight
static workloads and did not test proxy/upstream readiness. Host contention
still prevents interpreting several observed rates as server capacity. The
upstream orchestration uses the existing trusted fixture and rejects its CPU
utilization above 90%; a complete accepted proxy measurement remains necessary
to validate that execution path. Raw artifacts record exact tool hashes so
later tool changes cannot silently alter the meaning of these runs.
