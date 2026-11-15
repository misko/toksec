# Executable evaluation code

This directory contains checker code and calibration fixtures, not stored results.
The visibility catalog distinguishes minimal builder smoke cases from independent
host API cases. Stage definitions select checks; `toksec/` runs and benchmarks them.
Stage 10 has a separate partial checker in `stage10/checks.py`.

Parent reports and figures belong in a raw run's `evaluation/<id>/`, then in
`results/stage-XX/LANGUAGE/evaluation/<id>/` after publication. Framework regression
tests live in `tests/`. Neither this checker source nor test implementation fixtures
are included in current builder inputs.
