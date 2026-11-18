# Security audit — run 6baf167b — release/000001 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

This decoder carries an explicit c<32||c==127 test, so all six control-byte shapes are 400 and the encoded filename is unreachable. This is the boundary that makes the finding build-specific rather than family-wide.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The path decoder rejects bytes below 32, so no CRLF directory split is reachable | line 62 (`decodepath`) | `evidence/ev_r12_U_6baf167b_refusals.txt` `evidence/ev_r12_U_ctl_6baf167b.txt` |

## Findings

### SEC-001 — The path decoder rejects bytes below 32, so no CRLF directory split is reachable

This decoder carries an explicit c<32||c==127 test, so all six control-byte shapes are 400 and the encoded filename is unreachable. This is the boundary that makes the finding build-specific rather than family-wide.

Evidence: `evidence/ev_r12_U_6baf167b_refusals.txt` `evidence/ev_r12_U_ctl_6baf167b.txt`

## Artifact index

- `evidence/ev_r12_U_6baf167b_refusals.txt`
- `evidence/ev_r12_U_ctl_6baf167b.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
