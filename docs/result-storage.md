# Result storage and artifact contracts

The controller owns filenames, Git metadata, and release publication. The builder
submits source through controller tools. The parent owns independent evaluation
and permanent publication. Neither the builder's claims nor smoke success can
create a parent acceptance result.

## Contracts and instructions

`contracts/artifact.schema.json` defines the builder's source and release format.
Both runners generate `artifact.json`, copy it into the builder inputs, append the
same JSON to the launch packet, and pin its SHA-256 in the run manifest. The shared
`stages/common/ARTIFACTS.md` explains ownership. `RULES.md` describes tagging and
correctness-first grading. Stage and language instructions define server behavior
and permitted dependencies.

`contracts/evaluation.schema.json` defines the parent evaluation record. The
standard-library validator in `toksec/artifacts.py` rejects unsupported shapes.
The publisher also checks paths and file hashes. Schema validity alone does not
prove a server correct.

Existing frozen runs retain their original instructions. During migration, an
inferred format contract is stored as `provenance/artifact.json` and labeled
`reconstructed_for_storage`. It is not placed in the historical builder inputs.

## Permanent layout

Every new run has one persisted `run_id`, generated at preparation. The raw run,
published entry, and parent evaluations use that same identity. A typical ID is
`stage-01__cpp__20261115T143000Z__0679074ae618__a1b2c3d4`. The final suffix prevents
collisions. The timestamp is preparation time; start time is recorded separately.

Published runs retain separate directories. `index.json` selects the latest
started run per stage and language, independently of publication order, and
`README.md` provides the same view. Publishing an older run never replaces a newer
run's evidence. Different models, budgets, inputs, and evaluator fingerprints remain
separate experiments and must not be pooled into one score.

```text
results/
  README.md
  index.json
  <run-id>/
    run.json
    README.md
    sha256.json
    migration.json
    inputs/
      artifact.json
      manifest.json
      launch-packet.md
      builder-inputs/
      attempts/
    implementation/
      implementation.bundle
      releases.json
      source/main.cpp
      releases/release-000001.cpp
      evidence/
    accounting/
      ledger.json
      attempts/
    evaluation/
      <evaluation-id>/
        evaluation.json
        report.md
        api.json
        performance.json
        figures/
        raw/
    provenance/
      artifact.json
      legacy/
```

Files appear only when evidence exists. For example, the published Stage 5 snapshot
has no completed submission bundle. Rust uses `main.rs`. The Git bundle preserves
all tags from a run; source/ contains the last tagged submission. Development
smoke reports and builder notes belong under implementation/evidence/, never in
parent grading evidence.

Parent reports and figures belong exclusively under evaluation/. The parent may
evaluate the same implementation more than once. Each evaluation identifies the
run, release tag, server commit, source hash, contract hash, evaluator hash, and environment.
New runs record `toksec_commit` at preparation. New evaluations record their own
`toksec_commit` and `toksec_dirty`; tagged grading carries `run_toksec_commit` too.
These framework commits are separate from the submitted server’s `release.commit`.
Historical records without this evidence are not assigned a current commit.
A report with missing historical identity says so. It cannot claim verified full
acceptance. `run.json` supplies paths to the current implementation and evaluation.

## Evaluate and publish a run

Run these commands from the repository root. Compilation and candidate execution
remain sandboxed. These commands do not make model API calls.

For Stages 1–5, grade the last completed tag with the full API suite and then the
performance workloads, provided the API gate passes:

```sh
python3 evaluate.py --run .runs/CAMPAIGN/runs/RUN --section performance
python3 scripts/publish_results.py --run .runs/CAMPAIGN/runs/RUN
```

The default evaluation output is `.runs/CAMPAIGN/runs/RUN/evaluation/<id>/`.
The evaluator creates the machine-readable envelope and report there. Put figures
derived from that evaluation's measurements in its figures/ directory before
publication. An explicit output directory remains available for diagnostics;
publication automatically collects evaluations in the run's evaluation/ directory.

Stage 10 currently has only partial independent API coverage:

```sh
python3 evaluate.py --section api --run RUN_PATH
python3 scripts/publish_results.py --run .runs/RUN
```

Stage 10 reports remain partial even when every implemented check passes. A full
suite must exist before a report can establish full-stage acceptance.

The publisher derives `results/<run-id>/` from the persisted and validated run identity,
preserves the immutable bundle, and separates implementation evidence from parent
reports. It copies an explicit allowlist, excluding API conversations and credentials.
Test TLS keys supplied as fixtures are public test material. Republishing the same
run preserves its parent evaluations. Publishing another run creates its own directory and never reuses the
old run's reports. Republish the same run to add evaluations; existing evaluation
IDs cannot change their evidence. Published snapshots include checksums; add later evaluations to
the raw run and republish rather than modifying an existing evaluation in place.

Performance is skipped after failed API correctness and earns zero credit. A skipped
benchmark has no measured throughput or latency. Ineligible measurements, including
load-generator saturation, retain their diagnostic evidence without performance
credit. The report distinguishes partial coverage, failed checks, unrun tests,
and invalid measurements.

## Historical results

Existing `results/stage-XX/LANGUAGE/` snapshots remain at their original paths with
unchanged contents. The index can discover these alongside new run-ID directories.
No new framework commit is inferred for old records. Historical IDs, protocol
labels, figures, and source hashes retain their meaning.

The migration command below concerns older flat snapshots. It does not rename or
rewrite already migrated historical result directories.

## Migrate existing results

Preview and validate every byte mapping before applying the migration:

```sh
python3 scripts/migrate_results.py
python3 scripts/migrate_results.py --apply
```

The migration preserves existing sources, bundles, instructions, ledgers, reports,
and figures. `migration.json` maps each original file to its new path and checksum.
Unknown files and symlinks stop migration. Repeating the command verifies the migrated
snapshot without changing it. Migration never starts a model or re-runs server tests.
Historical grades and missing evidence keep their original meaning.

The bulk refresh command uses the same publication code:

```sh
python3 scripts/refresh_results.py \
  --source . \
  --source /home/mouse9911/gits/toksec-cpp \
  --source /home/mouse9911/gits/toksec-stages \
  --source /home/mouse9911/gits/toksec-stage5-cpp
```

Stages without published runs have no placeholder implementation. Currently the
inventory contains Stage 1 and Stage 2 in Rust and C++, and Stage 5 and Stage 10 in
C++. Historical raw campaigns remain in their original worktrees. Older published
results also remain in Git history at `f61d564` and in the local backup at
`/home/mouse9911/gits/toksec-archive/results-cleanup-20261114T190934Z/`.
