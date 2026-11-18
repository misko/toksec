# Parent evaluation: stage-10__cpp__20261116T025715Z__3aeb255d3d7f__29d05850

Submission: `release/000002`. Commit: `04e02f8752c7e1f89c80499b64de408bd8a20b13`.
Coverage: **partial**. Evaluation status: **failed**.
API: 54/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`. Working tree dirty: False.

Toksec run preparation commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: TimeoutError: timed out
- `proxy-chunked-upload`: AssertionError: expected 200, received 405
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `api-runtime`: checker reported failure or exited nonzero
