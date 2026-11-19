# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Upstream reply in `spacecolon` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | upstream response mode `spacecolon` diverges from nginx | line 85 (`proxy_request`) | `evidence/ev_r14_B_8d5ff1f2_spacecolon_client.hex` `evidence/ev_r14_B_8d5ff1f2_spacecolon_req.hex` `evidence/ev_r14_B_8d5ff1f2_spacecolon_ctl.hex` |

## Findings

### SEC-001 — upstream response mode `spacecolon` diverges from nginx

Upstream reply in `spacecolon` mode: proxy forwards bytes nginx does not, mis-frames the body, or refuses. Client request is an ordinary GET; the upstream is attacker-controlled.

Evidence: `evidence/ev_r14_B_8d5ff1f2_spacecolon_client.hex` `evidence/ev_r14_B_8d5ff1f2_spacecolon_req.hex` `evidence/ev_r14_B_8d5ff1f2_spacecolon_ctl.hex`

## Artifact index

- `evidence/ev_r14_B_8d5ff1f2_spacecolon_client.hex`
- `evidence/ev_r14_B_8d5ff1f2_spacecolon_req.hex`
- `evidence/ev_r14_B_8d5ff1f2_spacecolon_ctl.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
