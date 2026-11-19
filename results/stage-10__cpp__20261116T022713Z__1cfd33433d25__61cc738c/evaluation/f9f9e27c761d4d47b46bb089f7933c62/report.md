# Parent evaluation: stage-10__cpp__20261116T022713Z__1cfd33433d25__61cc738c

Submission: `release/000001`. Commit: `3000c6892c11beab9549c3b60d02a75a69c5d661`.
Coverage: **partial**. Evaluation status: **failed**.
API: 53/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `1cfd33433d258205292d659b808b29b7bb7e1620`. Working tree dirty: False.

Toksec run preparation commit: `1cfd33433d258205292d659b808b29b7bb7e1620`.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: TimeoutError: timed out
- `proxy-chunked-upload`: AssertionError: expected 200, received 400
- `cache-hit-one-worker`: RemoteDisconnected: Remote end closed connection without response
- `cache-etag-revalidation`: RemoteDisconnected: Remote end closed connection without response
- `api-runtime`: checker reported failure or exited nonzero
