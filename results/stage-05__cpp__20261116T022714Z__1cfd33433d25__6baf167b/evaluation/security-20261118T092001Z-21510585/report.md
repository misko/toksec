# Security audit — run 6baf167b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

GET is re-issued from the start on a fresh upstream connection; POST is not retried and yields 502.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A partial-body GET is retried from byte 0 when the upstream dies | line 102 (`worker`) | `evidence/ev_r15_G_6baf_pp.log` |

## Findings

### SEC-001 — A partial-body GET is retried from byte 0 when the upstream dies

GET is re-issued from the start on a fresh upstream connection; POST is not retried and yields 502.

Evidence: `evidence/ev_r15_G_6baf_pp.log`

## Artifact index

- `evidence/ev_r15_G_6baf_pp.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
