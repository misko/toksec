# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | branch-coverage: previously untested branch `keepsec` | line 87 (`keepsec`) | `evidence/ev_r14_D_f5_keepalive_timeout_8d5f.json` |

## Findings

### SEC-001 — branch-coverage: previously untested branch `keepsec`

Branch enumerated in the round-14 coverage sweep and driven with a targeted test after a passing control.

Evidence: `evidence/ev_r14_D_f5_keepalive_timeout_8d5f.json`

## Artifact index

- `evidence/ev_r14_D_f5_keepalive_timeout_8d5f.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
