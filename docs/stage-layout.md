# Stage definitions and generated inputs

`stages/` is the editable source of stage requirements and grading suites.
Use `stage-01` for directory names and machine identifiers, `Stage 1` in prose,
and integer `stage` fields in JSON. The shared formatter lives in
`toksec/stages.py`. Python components in these directories load through its
module selector. Protocol version directories are not part of current inputs.

```text
RULES.md
stages/
  common/                     Shared interfaces and artifact rules
    grading/                  Reusable API checks, workload helpers, and catalog
      fixtures/               Host-only calibration probe
    smoke/                    Minimal development checks and ordinary fixtures
  capabilities/               Reusable requirements
  languages/                  Rust and C++ restrictions
  stage-01/ ... stage-05/      SPEC.md and profile.json
    grading/                  api.py and performance.py
  stage-10/                   Stage 10 instructions, fixtures, packet assembly
    grading/                  api.py, checks.py, and performance.py
.generated/packets/            Optional current previews, ignored by Git
```

Each stage's `grading/api.py` defines its API suite. Its `grading/performance.py`
defines its workload selection. Suites reuse shared checks without duplicating
their implementations. The framework in `toksec/` runs the suites through
`evaluate.py`; `tests/` verifies that framework and the grading machinery.
Parent reports remain in `results/<run-id>/evaluation/<id>/`, separate from
the grading source and submitted implementation.

Preparation assembles English instructions from these definitions and freezes the
selected files in the run's `builder-inputs/` and `launch-packet.md`. It never reads
archived packets. The sandbox receives an explicit allowlist, not the whole stage
directory or comprehensive parent tests. No starter code is provided.
The `grading/` location is an ownership convention; the explicit input allowlist
enforces builder visibility. Moving code does not expand the builder's inputs.

Generate optional previews without model calls:

```sh
python3 -m toksec publish --language cpp
python3 -m toksec publish --stage 10 --language rust
```

These write `stage-01.md` / `stage-01.json`, or the selected stage, under
`.generated/packets/LANGUAGE/`. `--output DIRECTORY` selects another destination.
Edit canonical sources, not generated previews. `--level` remains an alias for
`--stage`; historical `level` JSON fields remain readable. Conflicting fields fail.

New runs record the full `toksec_commit` SHA and require a clean Git checkout.
Their names include the stage, language, UTC timestamp, abbreviated commit, and a
random suffix to avoid collisions. Preparation persists this name as `run_id`.
Raw directories, published `results/<run-id>/` entries and parent reports retain
the same ID, including after an operational directory is relocated. Commit
framework changes before preparation.
Each evaluation separately records its evaluator `toksec_commit` and
`toksec_dirty` state. Tagged evaluations also record `run_toksec_commit` from the
run manifest when available. Input and evaluator hashes remain required evidence;
the submitted server's Git commit is a separate identity.

Historical runs, reports, and manifests retain their original paths, protocol
labels and missing provenance. Never assign the current checkout's commit to old
evidence. Use an old run's recorded checkout to reproduce its evaluator.

Stage 10 uses the same public runner and result layout. Its API coverage remains
partial and performance measurements provisional, with no final performance credit.

Historical generated packets are preserved in [Git history](https://github.com/misko/toksec/tree/37d353034de935e32e40c31f71a44dbbc473e7b2/archive/task-packets).
Frozen instructions supplied to measured runs remain in their published inputs.
