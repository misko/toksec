# Results storage

`results/` is the curated view: one latest eligible run per stage and language.
Rust and C++ remain separate experiments. An eligible run must have started,
received no starter code, and received only minimal smoke feedback. Full-feedback,
seeded and older unknown-policy runs do not enter this view, even if newer.

```text
results/
  README.md                       # current inventory, protocol and status
  index.json                      # machine-readable inventory
  stage-01/{cpp,rust}/             # one run per language
  stage-02/{cpp,rust}/
  stage-05/cpp/                    # current run; snapshot until refreshed
    run.json                      # identity, provenance and compatibility
    README.md
    launch-packet.md               # exact instructions
    manifest.json
    specification.json
    timeline.json                 # only after independent grading completes
    correctness.png
    performance.png
    implementation.bundle         # all tags from this one run
    release-*.cpp                 # source and grading evidence per tag
    ledger.json                   # completed campaign accounting

diagnostics/calibration/http-v8/   # harness diagnostics, not server results
fixtures/accounting/               # historical accounting fixture used by tests
```

Stages 3 and 4 currently have no runs and no result directories. Each current run
retains its periodic releases: “one run” does not mean deleting its earlier tags.

Folders are stable; timestamp/model/protocol belong in `run.json`. The human-readable
run ID uses UTC:

`2026-11-14T19-02-32Z__stage-05__cpp__gpt-6.1-terra__http-v8__<fingerprint>`

The latest C++ Stages 1–2 used v7, Rust Stages 1–2 used v6, and Stage 5 uses v8.
Their minimal-input policy matches, but their evaluation protocols are not identical.
Do not combine scores across framework fingerprints, languages, model settings,
budgets or wall ceilings. A new protocol with no run has no baseline; do not silently
fill it with a historical score. Current results are an inventory, not a leaderboard.

## Refresh

```sh
python3 scripts/refresh_results.py \
  --source . \
  --source /home/mouse9911/gits/toksec-cpp \
  --source /home/mouse9911/gits/toksec-stages \
  --source /home/mouse9911/gits/toksec-stage5-cpp
```

The publisher reads original manifests and never changes raw campaigns. While a
builder is running it publishes provenance and instructions, not a live or final
grade. Refresh after grading to populate plots and tagged artifacts. The complete
frozen source set must be supplied each time. API response/conversation logs and
credentials are never copied into published results.

Old published folders were removed from the working results tree, with a local
backup under `/home/mouse9911/gits/toksec-archive/results-cleanup-20261114T190934Z/`.
They also remain in Git history at `f61d564`. Raw campaigns in older worktrees are
kept in place because their records contain absolute paths and their graders are
fingerprinted. They are historical provenance, not current results. In particular,
no moving or rewriting occurred in the active Stage 5 campaign.

Accounting tests previously depended on a pilot ledger inside results/. That
fixture now lives under fixtures/accounting so removing old visible results cannot
break budget enforcement. This change does not alter charges or budget rules.

## Stage 10 experimental snapshot

`results/stage-10/cpp/` preserves the first Stage 10 C++ Terra campaign separately
from the Stage 1–5 protocols. It includes all seven tags in a Git bundle, per-tag
source and smoke results, final partial API grading, exact supplied inputs and
conservative accounting for both attempts under the single $2 cap. It has no
performance measurements or full-stage acceptance. `sha256.json` inventories the
published files. Raw campaigns remain in `.runs/`.

Its `run.json` marks `inventory_management: preserved_snapshot`. The Stage 1–5
refresh script retains this entry without modifying its artifacts. Replacing this
snapshot requires an explicit Stage 10 publication rather than selecting it through
the legacy evaluator. The Git bundle can recreate the complete standalone repository.
