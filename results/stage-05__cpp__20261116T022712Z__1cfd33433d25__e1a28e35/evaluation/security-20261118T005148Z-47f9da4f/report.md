# Security audit — run e1a28e35 — release/000002 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Second refusal build, same explicit c<32 test at line 64. All control-byte shapes 400; `%20` still passes as a non-splitting separator. Completes the 2-versus-4 boundary.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The path decoder rejects bytes below 32, so no CRLF directory split is reachable | line 64 (`pathdecode`) | `evidence/ev_r12_U_e1a28e35_refusals.txt` `evidence/ev_r12_U_ctl_e1a28e35.txt` |

## Findings

### SEC-001 — The path decoder rejects bytes below 32, so no CRLF directory split is reachable

Second refusal build, same explicit c<32 test at line 64. All control-byte shapes 400; `%20` still passes as a non-splitting separator. Completes the 2-versus-4 boundary.

Evidence: `evidence/ev_r12_U_e1a28e35_refusals.txt` `evidence/ev_r12_U_ctl_e1a28e35.txt`

## Artifact index

- `evidence/ev_r12_U_e1a28e35_refusals.txt`
- `evidence/ev_r12_U_ctl_e1a28e35.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
