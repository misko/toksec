# Parent evaluation: stage-05__cpp__20261116T022714Z__1cfd33433d25__6baf167b

Submission: `release/000001`. Commit: `e2e5d47f1e1ce9888f301bfb7469217a8dadc1ee`.
Coverage: **full**. Evaluation status: **failed**.
API: 33/35 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `1cfd33433d258205292d659b808b29b7bb7e1620`. Working tree dirty: False.

Toksec run preparation commit: `1cfd33433d258205292d659b808b29b7bb7e1620`.

Failed checks:

- `proxy-pool-and-errors`: AssertionError: upstream connections not reused
- `graceful-stop`: AssertionError: listener remained open after SIGTERM
