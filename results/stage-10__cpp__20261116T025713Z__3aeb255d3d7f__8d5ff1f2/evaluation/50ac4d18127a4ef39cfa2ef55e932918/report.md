# Parent evaluation: stage-10__cpp__20261116T025713Z__3aeb255d3d7f__8d5ff1f2

Submission: `release/000002`. Commit: `8329f1f612b688e42c6e4bc439acef7c7eec09fb`.
Coverage: **partial**. Evaluation status: **failed**.
API: 53/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`. Working tree dirty: False.

Toksec run preparation commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: TimeoutError: timed out
- `proxy-chunked-upload`: AssertionError: expected 200, received 400
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `proxy-download-progress`: TimeoutError: timed out
- `api-runtime`: checker reported failure or exited nonzero
