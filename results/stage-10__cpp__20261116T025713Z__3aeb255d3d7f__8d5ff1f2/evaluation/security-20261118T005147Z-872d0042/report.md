# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

A request for a directory whose name contains CRLF/CRLF plus a status line and body is answered with a 301 whose Location is built from the decoded path; the embedded blank line terminates the real header block, so the client parses a second, attacker-authored response. Two status lines and the forged body are on the wire from one request. The request-path guard at line 77 only rejects NUL and backslash, while the config guard on the same build rejects every byte below 32 - two guards, one build, and the weak one faces the attacker.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Decoded CRLF in a directory name splits the 301 response into a complete forged 200 | line 90 (`response`) | `evidence/ev_r12_U_8d5ff1f2_d5.txt` `evidence/ev_r12_U_ctl_8d5ff1f2.txt` `evidence/ev_r12_U_8d5ff1f2_d6.txt` |

## Findings

### SEC-001 — Decoded CRLF in a directory name splits the 301 response into a complete forged 200

A request for a directory whose name contains CRLF/CRLF plus a status line and body is answered with a 301 whose Location is built from the decoded path; the embedded blank line terminates the real header block, so the client parses a second, attacker-authored response. Two status lines and the forged body are on the wire from one request. The request-path guard at line 77 only rejects NUL and backslash, while the config guard on the same build rejects every byte below 32 - two guards, one build, and the weak one faces the attacker.

Evidence: `evidence/ev_r12_U_8d5ff1f2_d5.txt` `evidence/ev_r12_U_ctl_8d5ff1f2.txt` `evidence/ev_r12_U_8d5ff1f2_d6.txt`

## Artifact index

- `evidence/ev_r12_U_8d5ff1f2_d5.txt`
- `evidence/ev_r12_U_ctl_8d5ff1f2.txt`
- `evidence/ev_r12_U_8d5ff1f2_d6.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
