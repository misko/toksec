# Security audit — run 6baf167b — release/000001 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Upstream reply in `statusline` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | upstream response mode `statusline` diverges from nginx | line 96 (`upstream_once`) | `evidence/ev_r14_B_6baf167b_statusline_client.hex` `evidence/ev_r14_B_6baf167b_statusline_req.hex` `evidence/ev_r14_B_6baf167b_statusline_ctl.hex` |

## Findings

### SEC-001 — upstream response mode `statusline` diverges from nginx

Upstream reply in `statusline` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

Evidence: `evidence/ev_r14_B_6baf167b_statusline_client.hex` `evidence/ev_r14_B_6baf167b_statusline_req.hex` `evidence/ev_r14_B_6baf167b_statusline_ctl.hex`

## Artifact index

- `evidence/ev_r14_B_6baf167b_statusline_client.hex`
- `evidence/ev_r14_B_6baf167b_statusline_req.hex`
- `evidence/ev_r14_B_6baf167b_statusline_ctl.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
