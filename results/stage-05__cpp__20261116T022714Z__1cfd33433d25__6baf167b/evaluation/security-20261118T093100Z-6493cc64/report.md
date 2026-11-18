# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Negative: hop 1's own 4-token refusal is what forces the double-encoded form. Named so a later agent does not read it as a chain failure.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A 4-token upstream line is refused by hop 1, which is why the chain needs double encoding | line 71 (`find`) | `evidence/ev_r15_E_nearmiss_z2_hop1_egress.hex` |

## Findings

### SEC-001 — A 4-token upstream line is refused by hop 1, which is why the chain needs double encoding

Negative: hop 1's own 4-token refusal is what forces the double-encoded form. Named so a later agent does not read it as a chain failure.

Evidence: `evidence/ev_r15_E_nearmiss_z2_hop1_egress.hex`

## Artifact index

- `evidence/ev_r15_E_nearmiss_z2_hop1_egress.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
