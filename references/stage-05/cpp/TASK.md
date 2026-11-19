# Stage 5 cpp reference assignment

Requested model: gpt-6.1-sol, reasoning effort xhigh, as a native subagent.
Do not launch API model calls. Preserve the user's standard-processing preference.

Read `references/BUILDER.md`, `tasks/v8/cpp/level-5.md`,
`stages/common/INTERFACE.md`, `stages/common/BENCHMARK.md`, and
`stages/languages/cpp.md`. Inspect the full applicable host API cases in
`evaluation/api/` and their selection in `toksec/checks.py`.

Your exclusive source/report directory is `references/stage-05/cpp`.
Deliver `references/stage-05/cpp/main.cpp` and `references/stage-05/cpp/REPORT.md`.
Run commands from the repository root, choosing a new output directory each time:

```sh
python3 evaluate.py --section api --level 5 --language cpp --source references/stage-05/cpp/main.cpp --output .runs/references/stage-05-cpp/api-001
```

After full API success and coordination of exclusive benchmark resources:

```sh
python3 evaluate.py --section performance --level 5 --language cpp --source references/stage-05/cpp/main.cpp --output .runs/references/stage-05-cpp/performance-001
```

The performance command repeats the API gate before the declared workload matrix.
Retain failures and inconclusive results as evidence. Do not change harness files.
