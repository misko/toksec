# Parent evaluation: stage-10__cpp__20261116T025716Z__3aeb255d3d7f__6fb186ed

Submission: `release/000004`. Commit: `ecfd36b6e9fed47e9f3656dce23f8abaa0e1f1bd`.
Coverage: **partial**. Evaluation status: **failed**.
API: 52/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`. Working tree dirty: False.

Toksec run preparation commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: TimeoutError: timed out
- `host-alpha.test:0`: AssertionError: expected 400, received 200
- `header-limit`: AssertionError: expected 431, received 200
- `proxy-chunked-upload`: AssertionError: expected 200, received 400
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `api-runtime`: checker reported failure or exited nonzero
