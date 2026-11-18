# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The retry loop re-sends the request to the next upstream whenever attempt 1 fails, including when the failure happens after the upstream has already run the command. The attacker's split survives verbatim, so the second attempt executes again: two executions of a non-idempotent command from a single client request, with only attempt 2's output returned. The rebuilt target is byte-identical to attempt 1 apart from Host.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A failed upstream that already executed the command is retried, so one request executes twice | line 80 (`attempt`) | `evidence/ev_r12_X_ev_afdc_execfail.txt` `evidence/ev_r12_X_ev_afdc_close.txt` `evidence/ev_r12_X_ev_afdc_control.txt` |

## Findings

### SEC-001 — A failed upstream that already executed the command is retried, so one request executes twice

The retry loop re-sends the request to the next upstream whenever attempt 1 fails, including when the failure happens after the upstream has already run the command. The attacker's split survives verbatim, so the second attempt executes again: two executions of a non-idempotent command from a single client request, with only attempt 2's output returned. The rebuilt target is byte-identical to attempt 1 apart from Host.

Evidence: `evidence/ev_r12_X_ev_afdc_execfail.txt` `evidence/ev_r12_X_ev_afdc_close.txt` `evidence/ev_r12_X_ev_afdc_control.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_execfail.txt`
- `evidence/ev_r12_X_ev_afdc_close.txt`
- `evidence/ev_r12_X_ev_afdc_control.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
