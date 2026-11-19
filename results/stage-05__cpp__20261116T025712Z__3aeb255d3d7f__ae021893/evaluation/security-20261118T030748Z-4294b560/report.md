# Security audit — run ae — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

hopset plus client tokens controls what is forwarded, and the conditional re-add fires on any POST, so Connection: content-length is a no-op on framing while range/if-none-match/accept-encoding/authorization remain attacker-deletable and observable (304 to 200).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | All five client-nominated headers are deletable; framing is re-added so the POST desync cannot fire | line 64 (`msg+=`) | `evidence/ev_r12_W_ae021893_sem.log` `evidence/ev_r12_W_ae021893_poc.log` |

## Findings

### SEC-001 — All five client-nominated headers are deletable; framing is re-added so the POST desync cannot fire

hopset plus client tokens controls what is forwarded, and the conditional re-add fires on any POST, so Connection: content-length is a no-op on framing while range/if-none-match/accept-encoding/authorization remain attacker-deletable and observable (304 to 200).

Evidence: `evidence/ev_r12_W_ae021893_sem.log` `evidence/ev_r12_W_ae021893_poc.log`

## Artifact index

- `evidence/ev_r12_W_ae021893_sem.log`
- `evidence/ev_r12_W_ae021893_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
