# Parent evaluation: stage-10__cpp__20261116T022716Z__1cfd33433d25__063b0d5e

Submission: `release/000002`. Commit: `80867f23fd76ced38153728f6a813c082ae4a9d1`.
Coverage: **partial**. Evaluation status: **failed**.
API: 52/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `1cfd33433d258205292d659b808b29b7bb7e1620`. Working tree dirty: False.

Toksec run preparation commit: `1cfd33433d258205292d659b808b29b7bb7e1620`.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: TimeoutError: timed out
- `path-/../hello.txt`: AssertionError: expected 403, received 400
- `path-/%2e%2e/hello.txt`: AssertionError: expected 403, received 400
- `proxy-chunked-upload`: AssertionError: expected 200, received 400
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `api-runtime`: checker reported failure or exited nonzero
