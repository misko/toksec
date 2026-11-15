# Toksec

Use standard processing only. Set `service_tier = "default"` when the backend supports that field. Never enable Fast, priority, or Ultrafast processing.

The builder implements the task in its assigned workspace. It must not edit contracts, evaluators, run records, or accepted artifacts.

Keep preparation costs separate from measured builder costs. Do not launch a paid experiment without a verified way to enforce its authorized budget.

Never describe a prompt-based spending instruction as a hard budget. Never describe a shared-filesystem native subagent as an isolated builder sandbox.

Run `python3 -m unittest discover -s tests -v` after changes to the harness.

## Artifact placement

Use the generated `artifact.json` and schemas in `contracts/` for new builder runs.
Both runners use `toksec.artifacts`; do not duplicate source-format or tag rules.
The controller owns release metadata. The builder supplies source and release notes.

Publish through the shared result tooling. Derive the permanent destination from
the persisted `run_id`, validated against stage, language and preparation commit.
Store frozen source and Git bundles under `results/<run-id>/implementation/`.
Keep one identity across the raw run, publication, and parent evaluations.
The latest index selects by run start time, not publication time.
Preserve existing historical `results/stage-XX/LANGUAGE/` snapshots. Store supplied inputs under `inputs/`
and campaign accounting under `accounting/`.

After grading, run `python3 scripts/publish_results.py --run RAW_RUN` from the
repository root. Use the grader's default `RAW_RUN/evaluation/<id>/` output so the
publisher can collect the reports. Put derived figures in that evaluation's
`figures/` directory before publication. Never assemble result folders by hand.

The parent owns `evaluation/<evaluation-id>/`, including its evaluation envelope,
API results, performance results, report and figures. Pin each evaluation to the
run, release commit, source hash and evaluator identity. Never place parent reports
inside the submitted Git repository. Preserve partial and unavailable coverage;
a migration does not establish acceptance. API failure skips performance and earns
zero performance credit, not a measured throughput of zero.

Preserve historical run packets and raw campaigns. Do not retrofit a generated
artifact contract into an old builder's recorded inputs. A migrated inferred
contract must be identified as migration metadata.
