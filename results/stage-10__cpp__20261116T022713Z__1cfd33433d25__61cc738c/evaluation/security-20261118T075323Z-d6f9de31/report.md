# Security audit — run 61cc738c — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | branch-coverage: previously untested branch `toksec_` | line 49 (`toksec_`) | `evidence/ev_r14_D_f1_pipeline_depth_61cc.json` |

## Findings

### SEC-001 — branch-coverage: previously untested branch `toksec_`

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

Evidence: `evidence/ev_r14_D_f1_pipeline_depth_61cc.json`

## Artifact index

- `evidence/ev_r14_D_f1_pipeline_depth_61cc.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
