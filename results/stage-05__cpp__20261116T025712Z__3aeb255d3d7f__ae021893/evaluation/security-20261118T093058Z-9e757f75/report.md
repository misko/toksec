# Security audit — run ae021893 — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

No auth-carrying entry is stored, so the poison survives across users.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Store is gated the same way as lookup on the second build | line 70 (`storecache`) | `evidence/ev_r15_E_k5b_hop2_upstream.hex` |

## Findings

### SEC-001 — Store is gated the same way as lookup on the second build

No auth-carrying entry is stored, so the poison survives across users.

Evidence: `evidence/ev_r15_E_k5b_hop2_upstream.hex`

## Artifact index

- `evidence/ev_r15_E_k5b_hop2_upstream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
