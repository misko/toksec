# Visible and held-out suites

Status: enforced for Stage 1 and Stage 2 in rust-http-v6. Builder submissions,
revalidation, release evidence and checkpoints use only visible smoke checks.
The full grader remains host-only and runs after the campaign. Development
sandboxes contain only ordinary smoke/benchmark fixtures, not edge-case fixtures.

## Visible API smoke checks

Stage 1 gets one check: start with a valid configuration, GET an existing small
ASCII file with an ordinary HTTP/1.1 request, verify 200, exact bytes, matching
Content-Length and connection closure. This demonstrates the executable interface
and a successful request without teaching error handling.

Stage 2 gets three checks:

1. The same successful GET, using Connection: close.
2. HEAD for that existing file, checking status and representation length with no body.
3. Two ordinary sequential GETs over one persistent connection, verifying both responses.

Do not include missing files, empty files, binary files, malformed or missing
fields, oversized headers, timeouts, pipelining, slow clients or invalid config in
these smoke checks. These are grading cases or builder-authored tests.

## Visible performance feedback

Keep the declared 256/4096-client, 4/64-KiB ordinary-file matrices available for
hill climbing: fresh connections for Stage 1, fresh and persistent for Stage 2.
These exercise valid traffic only. Show throughput, latency, failures, CPU and
memory. This is development feedback gated by smoke acceptance, not a final grade.
Terra can decide whether and when to use it. Withholding all load feedback would
make measured optimization difficult.

## Held-out API grading

Use the complete catalog on the host, including the happy paths. Keep concrete
inputs, test code and results out of the builder conversation until the run ends.
Coverage includes files and paths, parsing and framing, configuration validation,
size/deadline boundaries, fragmentation, disconnects and recovery. Stage 2 adds
HEAD variants, persistence and ordered pipelines, limits, slow-client isolation
and backpressure. Every expectation must trace to an English contract requirement.
Freeze the catalog, parameters and seeds before the campaign. Apply identical
grading rules across compared runs. Use different valid file names and contents
from the smoke fixtures to detect implementations specialized to the examples.

## Held-out performance grading

After every required held-out API check passes, independently rerun the declared
matrix on the tagged source, using fresh file contents and repeated measurements.
The matrix and metric definitions remain disclosed. Hold out the actual data,
trial ordering and results, not undocumented scored workloads.

Additional pipelining, mixed-file, churn and sustained-load scenarios may be kept
as host diagnostics. They become scored workloads only after the English benchmark
contract declares them. Slow-client correctness belongs in required API grading.
If held-out API fails, skip final performance and assign zero performance credit,
regardless of any earlier development benchmark.

## Enforced separation

- Maintain one catalog with explicit visible-smoke and held-out membership.
- Builder packets list only smoke checks; retain the full English contract.
- submit_candidate and revalidate_candidate return smoke results only.
- Release validation preserves visible checks. Full grading happens after the run.
- Development benchmarks use smoke eligibility, distinctly labeled provisional.
- Context rollover, capacity, release metadata and reports must not leak held-out
  results, names or counts. Merely hiding checker source is insufficient.
- The host evaluate.py entry point and final tag analysis run the complete suite.
  Evaluate historical tags after the run to measure true progress without feedback.
- Add regression tests ensuring every builder tool and checkpoint respects the split.

The strict $3 shared cap and two-hour ceiling remain unchanged.
