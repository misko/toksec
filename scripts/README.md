# Operational commands

Run from the repository root. Use `--help` for the exact arguments.

| Script | Purpose | Model API calls |
|---|---|---|
| `run_series.py` | Run prepared campaigns sequentially, then analyze releases | Yes by default; `--grade-only` disables model calls |
| `analyze_releases.py` | Independently grade tagged releases with the recorded evaluator and create a timeline | No |
| `plot_releases.py` | Plot an existing analysis timeline | No |
| `calibrate_benchmarks.py` | Measure load-generator/calibration behavior with sandboxed fixtures | No |
| `publish_results.py` | Publish one raw run using the canonical artifact layout | No |
| `refresh_results.py` | Refresh the current Stage 1–5 inventory from frozen source worktrees | No |
| `migrate_results.py` | Validate or apply migration of older published result layouts | No |

New single-release grading defaults to `RUN_PATH/evaluation/<id>/`. The all-tags
analysis scripts retain their historical timeline format and explicit output path;
the publisher supports both. Preserve raw campaigns and use the original checkout
for historical evaluator fingerprints. Do not copy source, reports, or figures by
hand into published results; use the [artifact workflow](../docs/result-storage.md).

`record_security_evaluation.py` freezes a parent security report and curated
evidence against an exact tagged release. It makes no model calls and executes
no evidence. Publish the resulting record with `publish_results.py`. See
[security evaluations](../docs/result-storage.md#security-evaluations).
