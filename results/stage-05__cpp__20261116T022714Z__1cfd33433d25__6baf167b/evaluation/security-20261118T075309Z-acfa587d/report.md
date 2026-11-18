# Security audit — run 6baf167b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(400, reference 200+200)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `pipe_crlf` — 6baf167b decodepath | line 62 (`decodepath`) | `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_refnginx2_out.log` |

## Findings

### SEC-001 — negative for `pipe_crlf` — 6baf167b decodepath

(400, reference 200+200)

Evidence: `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_refnginx2_out.log`

## Artifact index

- `evidence/ev_r14_A_6baf167b_v2_out.log`
- `evidence/ev_r14_A_refnginx2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
