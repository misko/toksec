# Published experiment evidence

This tree is managed by the result publisher. Root `AGENTS.md` also applies.

Do not hand-create or edit run or evaluation folders here. This includes
supplementary security reports and Markdown-only reports. Multiple analyses of a
run belong in separate `evaluation/<evaluation-id>/` folders, each with a validated
`evaluation.json` and inventoried report and evidence files.

For a new security report:

1. Obtain the actual analyzed release and analysis metadata from the analyst.
2. Read `../docs/result-storage.md`, section "Security evaluations".
3. Run `scripts/record_security_evaluation.py` from the repository root against
   the raw run, with the actual tag, analysis JSON, report, and optional evidence.
4. Run `scripts/publish_results.py --run RAW_RUN` from the repository root.

Never infer the analyzed tag from whichever release is newest. Do not invent
missing provenance or retrofit contracts into historical builder inputs. If the
recording requirements cannot be satisfied, stop publication and explain what is
missing. A report-only folder is unregistered, not an exception to this workflow.

Preserve existing evidence and report bytes. Do not open report contents when the
user has prohibited reading them. Do not commit unrelated unregistered reports
as part of framework or documentation changes.
