# Security audit — run f2b3415b — release/000001 (round 11, lane Q)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same four stalls, silent zero-byte close, 64 stalled POSTs reset the 65th client, all 38 accepted shapes agree. `55z2fol` sends three co-buffered chunked POSTs and receives three `200`s correctly paired, so the stall is a slot-holding defect rather than a desync. The process additionally needs non-zero `cache_ttl_ms`/`cache_bytes` to start.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Same slot stall and 65th-connection reset; three co-buffered chunked POSTs stay correctly paired | line 100 (`maxconn`) | `evidence/ev_r11_Q_3aeb255d3d7f__f2b3415b_Z1.log` |

## Findings

### SEC-001 — Same slot stall and 65th-connection reset; three co-buffered chunked POSTs stay correctly paired

Same four stalls, silent zero-byte close, 64 stalled POSTs reset the 65th client, all 38 accepted shapes agree. `55z2fol` sends three co-buffered chunked POSTs and receives three `200`s correctly paired, so the stall is a slot-holding defect rather than a desync. The process additionally needs non-zero `cache_ttl_ms`/`cache_bytes` to start.

Evidence: `evidence/ev_r11_Q_3aeb255d3d7f__f2b3415b_Z1.log`

## Artifact index

- `evidence/ev_r11_Q_3aeb255d3d7f__f2b3415b_Z1.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
