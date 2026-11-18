# Security audit — run 6baf167b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(`Expect` never answered, deadline close)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | transfer — 6baf167b parse_request | line 70 (`parse_request`) | `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_expect_6baf.log` `evidence/ev_r14_A_probe_nginx_out.log` |

## Findings

### SEC-001 — transfer — 6baf167b parse_request

(`Expect` never answered, deadline close)

Evidence: `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_expect_6baf.log` `evidence/ev_r14_A_probe_nginx_out.log`

## Artifact index

- `evidence/ev_r14_A_6baf167b_v2_out.log`
- `evidence/ev_r14_A_expect_6baf.log`
- `evidence/ev_r14_A_probe_nginx_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
