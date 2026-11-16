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

Historical snapshots also use `results/<run-id>/`. Runs that predate canonical
commit-based names retain their recorded raw run IDs, for example
`level-1-0989d5c40297`. Missing framework commits remain missing. Migration does not
retroactively give old runs a modern name or rewrite their supplied instructions.

`run.json` records the old publication/evaluation IDs in `historical_ids` and the
former stage/language directory in `historical_path`. Existing evaluation JSON,
reports, figures, bundles, inputs and accounting retain their original bytes.
Their historical run IDs remain meaningful aliases, not newly issued evaluations.

`provenance/run-id-migration.json` maps every former file to its preserved path and
SHA-256. The old top-level `run.json`, `README.md`, and `sha256.json` are preserved
under `provenance/run-id-migration/original/`. The original results index and README
are retained under `results/provenance/run-id-migration/`.

## Migrate existing results

Preview and validate every byte mapping before applying the run-ID relocation:

```sh
python3 scripts/migrate_results.py --run-ids
python3 scripts/migrate_results.py --run-ids --apply
```

The command validates the entire batch, copies and verifies all targets before
removing old directories, then rebuilds the latest index. Destination collisions,
changed evidence and symlinks stop migration. An interrupted installation can be
rerun. Repeating a completed migration verifies preservation without changing the
published evidence. It never calls a model or reruns server acceptance tests.

The earlier flat-layout migration remains available without `--run-ids`. Normalize
flat snapshots first if needed, then relocate their directories. Both migrations
preserve historical grades and missing evidence.

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

## Security evaluations

Security analyses use `contracts/security-evaluation.schema.json` and
`kind: "security"`. Existing API/performance records retain their original schema.
The shared `validate_evaluation` entry point dispatches by kind.

Store each analysis under `RAW_RUN/evaluation/security-<timestamp>-<suffix>/`.
Publication preserves that ID at `results/<run-id>/evaluation/<evaluation-id>/`:

```text
evaluation.json       Release identity, analysis metadata, file hashes and sizes
report.md             Parent analysis report
evidence/             Selected logs, requests, reproductions, and supporting files
figures/              Optional analysis figures
```

Each security record requires the run ID, release tag, exact server Git commit,
source SHA-256, frozen artifact-contract SHA-256, evaluator SHA-256, current Toksec
commit and dirty state, environment, scope, methods, limitations, and findings.
`run_toksec_commit` remains null when historical preparation provenance is unknown.
The evaluator hash identifies the analysis scripts or an analysis-method manifest;
it is supplied by the analyst and is not a claim that Toksec verified the method.

Statuses are `completed`, `partial`, or `error`. Completion describes the declared
analysis, not proof that the server is secure. Findings have stable IDs, severity,
confirmation status, descriptions, and references to inventoried evidence files.
An empty findings list means no findings were recorded within the declared scope.
Security evaluations carry no API pass counts or performance credit and do not
replace those evaluations. Stage 10 coverage limitations remain unchanged.

Prepare an analysis JSON containing these fields, for example:

```json
{
  "evaluator_sha256": "<64 lowercase hex characters identifying the analysis method>",
  "environment": {"os": "Linux", "tool": "manual review"},
  "status": "partial",
  "scope": "HTTP request parsing in release/000001",
  "methods": ["Source review and malformed-request tests"],
  "limitations": ["Concurrency behavior was not assessed"],
  "findings": [{
    "id": "SEC-001",
    "title": "Observed parser discrepancy",
    "severity": "low",
    "status": "unconfirmed",
    "description": "Describe the observation and its implications here.",
    "evidence": ["evidence/parser.log"]
  }]
}
```

Replace the hash placeholder with the SHA-256 of your method manifest or tooling.
Then record the analysis and publish through the existing workflow:

```sh
python3 scripts/record_security_evaluation.py --run RAW_RUN \
  --tag release/000001 --analysis /path/to/analysis.json \
  --report /path/to/report.md --evidence /path/to/curated-evidence \
  --figures /path/to/figures
python3 scripts/publish_results.py --run RAW_RUN
```

`--evidence` and `--figures` are optional. Findings must reference evidence when
present. The recorder generates an ID, or accepts `--evaluation-id`, and resolves
the tag to its commit and source hash. Supply the tag actually analyzed. It
requires a raw run with its repository and frozen artifact contract; a historical
publication without those cannot be given invented provenance.

The recorder copies only the supplied report and curated evidence/figure trees.
It inventories each file by relative path, SHA-256, and byte count. Recording and
publishing never execute evidence or make model calls. Publication rejects changed
bytes, missing or unlisted files, symlinks, unsafe paths, and mismatched release
identity. Reports are append-only: use a new evaluation ID for a revised analysis.
Existing evaluations and historical results are not rewritten.

Supplementary and Markdown-only security reports use this same workflow. There
is no direct-placement exception. A folder containing `report.md` without
`evaluation.json` is unregistered; validation rejects it with recording guidance.
Publishing alone does not register a file already copied into `results/`.

For an existing unregistered report, preserve its bytes before reconciliation.
Obtain the exact analyzed release and analysis metadata from its author, rather
than infer them from a date or the latest tag. If report reading is prohibited,
do not open it to fill metadata gaps. A historical run without its original
artifact contract cannot use the current recorder; do not create a substitute
contract in the historical run to bypass that requirement. Resolve provenance
explicitly before publication, and leave the report intact while blocked.
