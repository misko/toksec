# Security audit — run e1a2 — release/000002 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The parser rejects the continuation outright, giving a 502 instead of the 44bf7f35 silent drop. Recorded so the fold finding stays build-specific.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Obs-fold is refused before the field is read, so the value is never truncated | line 61 (`parseheaders`) | `evidence/ev_r12_V_e1a2_ae02_refusal.txt` |

## Findings

### SEC-001 — Obs-fold is refused before the field is read, so the value is never truncated

The parser rejects the continuation outright, giving a 502 instead of the 44bf7f35 silent drop. Recorded so the fold finding stays build-specific.

Evidence: `evidence/ev_r12_V_e1a2_ae02_refusal.txt`

## Artifact index

- `evidence/ev_r12_V_e1a2_ae02_refusal.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
