# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | branch-coverage: previously untested branch `hbytes` | line 70 (`hbytes`) | `evidence/ev_r14_D_f12_6baf_boundaries.json` |

## Findings

### SEC-001 — branch-coverage: previously untested branch `hbytes`

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

Evidence: `evidence/ev_r14_D_f12_6baf_boundaries.json`

## Artifact index

- `evidence/ev_r14_D_f12_6baf_boundaries.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
