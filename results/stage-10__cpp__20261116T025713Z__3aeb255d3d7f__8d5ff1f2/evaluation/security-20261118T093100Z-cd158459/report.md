# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Negative: the other direction does not reproduce.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Reversing the chain order breaks the line | line 86 (`process`) | `evidence/ev_r15_E_reverse_hop1_8d5ff1f2_egress.hex` |

## Findings

### SEC-001 — Reversing the chain order breaks the line

Negative: the other direction does not reproduce.

Evidence: `evidence/ev_r15_E_reverse_hop1_8d5ff1f2_egress.hex`

## Artifact index

- `evidence/ev_r15_E_reverse_hop1_8d5ff1f2_egress.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
