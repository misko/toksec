# Security audit — run 063b0d5e — release/000002 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Upstream reply in `1xx` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | upstream response mode `1xx` diverges from nginx | line 68 (`upstream_parse`) | `evidence/ev_r14_B_063b0d5e_1xx_client.hex` `evidence/ev_r14_B_063b0d5e_1xx_req.hex` `evidence/ev_r14_B_063b0d5e_1xx_ctl.hex` |

## Findings

### SEC-001 — upstream response mode `1xx` diverges from nginx

Upstream reply in `1xx` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

Evidence: `evidence/ev_r14_B_063b0d5e_1xx_client.hex` `evidence/ev_r14_B_063b0d5e_1xx_req.hex` `evidence/ev_r14_B_063b0d5e_1xx_ctl.hex`

## Artifact index

- `evidence/ev_r14_B_063b0d5e_1xx_client.hex`
- `evidence/ev_r14_B_063b0d5e_1xx_req.hex`
- `evidence/ev_r14_B_063b0d5e_1xx_ctl.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
