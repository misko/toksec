# Security audit — run 44bf — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Completes the three-build NUL boundary: all three relays carry the byte, so the truncation is a client-side property rather than a per-build accident.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A NUL inside a header value is relayed on the third pass-raw build | line 87 (`trim`) | `evidence/ev_r12_V_44bf_nul.txt` |

## Findings

### SEC-001 — A NUL inside a header value is relayed on the third pass-raw build

Completes the three-build NUL boundary: all three relays carry the byte, so the truncation is a client-side property rather than a per-build accident.

Evidence: `evidence/ev_r12_V_44bf_nul.txt`

## Artifact index

- `evidence/ev_r12_V_44bf_nul.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
