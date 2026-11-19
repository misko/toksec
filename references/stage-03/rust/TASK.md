# Stage 3 rust reference assignment

Requested model: gpt-6.1-sol, reasoning effort xhigh, as a native subagent.
Do not launch API model calls. Preserve the user's standard-processing preference.

Read `references/BUILDER.md`, `tasks/v8/rust/level-3.md`,
`stages/common/INTERFACE.md`, `stages/common/BENCHMARK.md`, and
`stages/languages/rust.md`. Inspect the full applicable host API cases in
`evaluation/api/` and their selection in `toksec/checks.py`.

Your exclusive source/report directory is `references/stage-03/rust`.
Deliver `references/stage-03/rust/main.rs` and `references/stage-03/rust/REPORT.md`.
Run commands from the repository root, choosing a new output directory each time:

```sh
python3 evaluate.py --section api --level 3 --language rust --source references/stage-03/rust/main.rs --output .runs/references/stage-03-rust/api-001
```

After full API success and coordination of exclusive benchmark resources:

```sh
python3 evaluate.py --section performance --level 3 --language rust --source references/stage-03/rust/main.rs --output .runs/references/stage-03-rust/performance-001
```

The performance command repeats the API gate before the declared workload matrix.
Retain failures and inconclusive results as evidence. Do not change harness files.
