# Security audit — run ae021893 — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

negative — `readconfig` trims the value before it can be concatenated. Negative result: control first, then payload, upstream bytes captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative — `readconfig` trims the value before it can be concatenated | line 45 (`readconfig`) | `evidence/ev_r14_B_ae021893_1xx.txt` `evidence/ev_r14_B_ae021893_1xx_client.hex` `evidence/ev_r14_B_ae021893_1xx_ctl.hex` `evidence/ev_r14_B_ae021893_1xx_req.hex` |

## Findings

### SEC-001 — negative — `readconfig` trims the value before it can be concatenated

negative — `readconfig` trims the value before it can be concatenated. Negative result: control first, then payload, upstream bytes captured.

Evidence: `evidence/ev_r14_B_ae021893_1xx.txt` `evidence/ev_r14_B_ae021893_1xx_client.hex` `evidence/ev_r14_B_ae021893_1xx_ctl.hex` `evidence/ev_r14_B_ae021893_1xx_req.hex`

## Artifact index

- `evidence/ev_r14_B_ae021893_1xx.txt`
- `evidence/ev_r14_B_ae021893_1xx_client.hex`
- `evidence/ev_r14_B_ae021893_1xx_ctl.hex`
- `evidence/ev_r14_B_ae021893_1xx_req.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
