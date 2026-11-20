# Operational commands

Run from the repository root. Use `--help` for the exact arguments.

| Script | Purpose | Model API calls |
|---|---|---|
| `run_series.py` | Run prepared campaigns sequentially, then analyze releases | Yes by default; `--grade-only` disables model calls |
| `analyze_releases.py` | Independently grade each release and create a time and spend timeline. Explicit comparison mode remeasures the frozen contract with the current evaluator. | No |
| `plot_releases.py` | Plot an existing analysis timeline | No |
| `calibrate_benchmarks.py` | Measure load-generator/calibration behavior with sandboxed fixtures | No |
| `publish_results.py` | Publish one raw run using the canonical artifact layout | No |
| `refresh_results.py` | Refresh the current Stage 1–5 inventory from frozen source worktrees | No |
| `migrate_results.py` | Validate or apply migration of older published result layouts | No |

Single-release grading and all-tag analysis write each parent envelope under `RUN_PATH/evaluation/<id>/`. A series workspace retains the Git export and `timeline.json`, including tag-time spend and per-tag evaluation IDs. The [CLI walkthrough](../docs/cli-walkthrough.md) shows how to render and publish the final release's figures. Independent measurement with a changed evaluator requires explicit comparison mode. Archived flat analyses use the historical publication path.

`record_security_evaluation.py` freezes a parent security report and curated
evidence against an exact tagged release. It makes no model calls and executes
no evidence. Publish the resulting record with `publish_results.py`. See
[security evaluations](../docs/result-storage.md#security-evaluations).

`run_parallel.py prepare|run|status|finalize` operates independently budgeted
Terra sandbox batches with disjoint CPU slots. See [parallel runs](../docs/parallel-runs.md).
