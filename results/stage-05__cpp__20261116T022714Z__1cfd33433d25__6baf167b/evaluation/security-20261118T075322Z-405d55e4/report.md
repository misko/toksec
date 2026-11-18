# Security audit — run 6baf167b — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

negative — `Connection:`-driven `authorization` deletion reaches upstream without changing key. Negative result: control first, then payload, upstream bytes captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative — `Connection:`-driven `authorization` deletion reaches upstream without changing key | line 94 (`hop`) | `evidence/ev_r14_A_6baf167b_plain.log` `evidence/ev_r14_A_6baf167b_v2.log` `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_up_6baf167b_plain.log` |

## Findings

### SEC-001 — negative — `Connection:`-driven `authorization` deletion reaches upstream without changing key

negative — `Connection:`-driven `authorization` deletion reaches upstream without changing key. Negative result: control first, then payload, upstream bytes captured.

Evidence: `evidence/ev_r14_A_6baf167b_plain.log` `evidence/ev_r14_A_6baf167b_v2.log` `evidence/ev_r14_A_6baf167b_v2_out.log` `evidence/ev_r14_A_up_6baf167b_plain.log`

## Artifact index

- `evidence/ev_r14_A_6baf167b_plain.log`
- `evidence/ev_r14_A_6baf167b_v2.log`
- `evidence/ev_r14_A_6baf167b_v2_out.log`
- `evidence/ev_r14_A_up_6baf167b_plain.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
