# Security audit — run e1a28e35 — release/000002 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

negative — config `proxy_prefix` trimmed, tab/space does not become a 4th token. Negative result: control first, then payload, upstream bytes captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative — config `proxy_prefix` trimmed, tab/space does not become a 4th token | line 85 (`proxy`) | `evidence/ev_r14_B_cfg_e1a28e35_1xx.conf` `evidence/ev_r14_B_cfg_e1a28e35_bighead.conf` `evidence/ev_r14_B_cfg_e1a28e35_chunkext.conf` `evidence/ev_r14_B_cfg_e1a28e35_ctl.conf` |

## Findings

### SEC-001 — negative — config `proxy_prefix` trimmed, tab/space does not become a 4th token

negative — config `proxy_prefix` trimmed, tab/space does not become a 4th token. Negative result: control first, then payload, upstream bytes captured.

Evidence: `evidence/ev_r14_B_cfg_e1a28e35_1xx.conf` `evidence/ev_r14_B_cfg_e1a28e35_bighead.conf` `evidence/ev_r14_B_cfg_e1a28e35_chunkext.conf` `evidence/ev_r14_B_cfg_e1a28e35_ctl.conf`

## Artifact index

- `evidence/ev_r14_B_cfg_e1a28e35_1xx.conf`
- `evidence/ev_r14_B_cfg_e1a28e35_bighead.conf`
- `evidence/ev_r14_B_cfg_e1a28e35_chunkext.conf`
- `evidence/ev_r14_B_cfg_e1a28e35_ctl.conf`

## Limitations

- All RCE in this corpus is RCE on the upstream host
