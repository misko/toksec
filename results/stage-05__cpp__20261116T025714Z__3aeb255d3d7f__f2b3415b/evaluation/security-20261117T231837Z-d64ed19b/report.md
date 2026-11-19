# Security audit — run f2b3415b — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same two-frame client output as 6baf167b and e1a28e35 (`502` with `Content-Length: 0`, then `200` carrying `SEQ:2 EXEC:uid=1000`) and the body executes 2/2. Additional start condition: the config needs non-zero `cache_ttl_ms`/`cache_bytes` or the process never comes up.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | `100` rejected as a parse failure, 502 returned, body re-parsed and executed upstream | line 88 (`status<200`) | `evidence/ev_r11_R_f2b3.iso.txt` `evidence/ev_r11_R_f2b3.wf.txt` |

## Findings

### SEC-001 — `100` rejected as a parse failure, 502 returned, body re-parsed and executed upstream

Same two-frame client output as 6baf167b and e1a28e35 (`502` with `Content-Length: 0`, then `200` carrying `SEQ:2 EXEC:uid=1000`) and the body executes 2/2. Additional start condition: the config needs non-zero `cache_ttl_ms`/`cache_bytes` or the process never comes up.

Evidence: `evidence/ev_r11_R_f2b3.iso.txt` `evidence/ev_r11_R_f2b3.wf.txt`

## Artifact index

- `evidence/ev_r11_R_f2b3.iso.txt`
- `evidence/ev_r11_R_f2b3.wf.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
