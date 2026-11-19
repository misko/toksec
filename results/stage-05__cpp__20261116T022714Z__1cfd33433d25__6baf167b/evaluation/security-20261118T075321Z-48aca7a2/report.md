# Security audit — run 6baf167b — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

negative — auth gate, key has no auth component; A-poisoned entry not served to B. Negative result: control first, then payload, upstream bytes captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative — auth gate, key has no auth component; A-poisoned entry not served to B | line 89 (`cached`) | `evidence/ev_r14_A_6baf167b_plain.log` `evidence/ev_r14_A_6baf167b_v2.log` `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_up_6baf167b_plain.log` |

## Findings

### SEC-001 — negative — auth gate, key has no auth component; A-poisoned entry not served to B

negative — auth gate, key has no auth component; A-poisoned entry not served to B. Negative result: control first, then payload, upstream bytes captured.

Evidence: `evidence/ev_r14_A_6baf167b_plain.log` `evidence/ev_r14_A_6baf167b_v2.log` `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_up_6baf167b_plain.log`

## Artifact index

- `evidence/ev_r14_A_6baf167b_plain.log`
- `evidence/ev_r14_A_6baf167b_v2.log`
- `evidence/ev_r14_A_6baf167b_v2_out.log`
- `evidence/ev_r14_A_up_6baf167b_plain.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
