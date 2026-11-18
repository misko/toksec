# Security audit — run e1a — release/000002 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same client-controlled deletion set with an unconditional Content-Length re-add from body.size(); deletion of framing names cannot desync, but the four semantic names are attacker-controlled.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | All five client-nominated headers are deletable; framing re-added unconditionally | line 84 (`msg=method`) | `evidence/ev_r12_W_e1a28e35_sem.log` `evidence/ev_r12_W_e1a28e35_poc.log` |

## Findings

### SEC-001 — All five client-nominated headers are deletable; framing re-added unconditionally

Same client-controlled deletion set with an unconditional Content-Length re-add from body.size(); deletion of framing names cannot desync, but the four semantic names are attacker-controlled.

Evidence: `evidence/ev_r12_W_e1a28e35_sem.log` `evidence/ev_r12_W_e1a28e35_poc.log`

## Artifact index

- `evidence/ev_r12_W_e1a28e35_sem.log`
- `evidence/ev_r12_W_e1a28e35_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
