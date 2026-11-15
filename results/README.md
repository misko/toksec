# Latest server experiments

One run per stage and language. Starter-code and comprehensive-feedback runs are excluded.
These entries have different evaluator versions: do not pool their scores or performance.
Stages without an eligible run have no result folder. Running entries are snapshots.

| Stage | Language | Protocol | Status | Latest run (UTC) |
|---|---|---|---|---|
| 1 | cpp | http-v7 | graded | [2026-11-14T05-14-27Z](stage-01/cpp/README.md) |
| 1 | rust | rust-http-v6 | graded | [2026-11-14T04-37-02Z](stage-01/rust/README.md) |
| 2 | cpp | http-v7 | graded | [2026-11-14T15-35-01Z](stage-02/cpp/README.md) |
| 2 | rust | rust-http-v6 | graded | [2026-11-14T05-07-35Z](stage-02/rust/README.md) |
| 5 | cpp | http-v8 | running | [2026-11-14T19-02-32Z](stage-05/cpp/README.md) |

| 10 | cpp | stage10-experimental | partially graded | [2026-11-15T17-26-37Z](stage-10/cpp/README.md) |

Refresh using scripts/refresh_results.py with the frozen source worktrees.
Historical experiments are preserved in Git history and a local external archive.
Calibration reports live under diagnostics/, not server results.
