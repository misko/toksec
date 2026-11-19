# Security audit — run 44bf7f35 — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(417, reference sends 100)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `Expect` — 44bf7f35 bad(417) | line 90 (`bad(417)`) | `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_refnginx2_out.log` |

## Findings

### SEC-001 — negative for `Expect` — 44bf7f35 bad(417)

(417, reference sends 100)

Evidence: `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_refnginx2_out.log`

## Artifact index

- `evidence/ev_r14_A_44bf7f35_v2_out.log`
- `evidence/ev_r14_A_refnginx2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
