# Security audit — run ae021893 — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

negative — target built as `"/"+rem.substr(c.proxy.size())`, prefix space already consumed. Negative result: control first, then payload, upstream bytes captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative — target built as `"/"+rem.substr(c.proxy.size())`, prefix space already consumed | line 64 (`upstream`) | `evidence/ev_r14_B_ae021893_1xx.txt` `evidence/ev_r14_B_ae021893_1xx_client.hex` `evidence/ev_r14_B_ae021893_1xx_ctl.hex` `evidence/ev_r14_B_ae021893_1xx_req.hex` |

## Findings

### SEC-001 — negative — target built as `"/"+rem.substr(c.proxy.size())`, prefix space already consumed

negative — target built as `"/"+rem.substr(c.proxy.size())`, prefix space already consumed. Negative result: control first, then payload, upstream bytes captured.

Evidence: `evidence/ev_r14_B_ae021893_1xx.txt` `evidence/ev_r14_B_ae021893_1xx_client.hex` `evidence/ev_r14_B_ae021893_1xx_ctl.hex` `evidence/ev_r14_B_ae021893_1xx_req.hex`

## Artifact index

- `evidence/ev_r14_B_ae021893_1xx.txt`
- `evidence/ev_r14_B_ae021893_1xx_client.hex`
- `evidence/ev_r14_B_ae021893_1xx_ctl.hex`
- `evidence/ev_r14_B_ae021893_1xx_req.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
