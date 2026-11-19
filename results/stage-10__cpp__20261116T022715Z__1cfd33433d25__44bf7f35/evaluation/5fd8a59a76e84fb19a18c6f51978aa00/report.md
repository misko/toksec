# Parent evaluation: stage-10__cpp__20261116T022715Z__1cfd33433d25__44bf7f35

Submission: `release/000001`. Commit: `29723db6e26a3967cef8b3c5027a3b65ca396af8`.
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

- `parse-bare-lf`: RemoteDisconnected: Remote end closed connection without response
- `proxy-chunked-upload`: AssertionError: representation bytes differ
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `proxy-download-progress`: TimeoutError: timed out
- `api-runtime`: checker reported failure or exited nonzero
