# Parent evaluation: 2026-11-15T17-26-37Z__stage-10__cpp__gpt-6.1-terra__stage10-experimental__f02ed71d

Submission: `release/000007`. Commit: `2ccd5686c32225c150fe06138fbf52d88c584f76`.
Coverage: **partial**. Evaluation status: **failed**.
API: 50/57 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Historical evidence is missing: contract_sha256.

This report does not establish full-stage acceptance.

Failed checks:

- `parse-bare-lf`: RemoteDisconnected: Remote end closed connection without response
- `framing-ambiguous-proxy`: AssertionError: expected 400, received 200
- `header-limit`: RemoteDisconnected: Remote end closed connection without response
- `proxy-chunked-response`: AssertionError: representation bytes differ
- `proxy-chunked-upload`: AssertionError: expected 200, received 405
- `cache-hit-one-worker`: AssertionError: unexpected upstream fetch count
- `proxy-download-progress`: TimeoutError: timed out
- `api-runtime`: checker reported failure or exited nonzero
