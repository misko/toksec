# Parent evaluation: stage-05__cpp__20261116T025712Z__3aeb255d3d7f__ae021893

Submission: `release/000001`. Commit: `e5b20e4a4c8a92c5166e843922fced3e2968d73d`.
Coverage: **full**. Evaluation status: **failed**.
API: 32/35 behavioral checks passed.
Performance: **skipped_api_failure**.

A skipped performance test has no measured throughput or latency.
Zero performance credit is not a measured throughput of zero.

See api.json and performance.json for evidence. Figures belong in figures/.

Toksec evaluator commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`. Working tree dirty: False.

Toksec run preparation commit: `3aeb255d3d7f5df4f396e71bf51273f0cc0cf565`.

Failed checks:

- `proxy-pool-and-errors`: AssertionError: upstream connections not reused
- `cache`: AssertionError: 
- `graceful-stop`: AssertionError: listener remained open after SIGTERM
