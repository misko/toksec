# Security audit — run 6fb186ed — release/000004 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same sink as 8d5ff1f2: the 301 Location is concatenated from the decoded path with no re-check, so a directory name carrying CRLF and a full status line yields two responses in one client stream, including the attacker body. The decoder at line 62 rejects only NUL and backslash, while the config validator on the same build rejects bytes below 32.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Decoded CRLF in a directory name splits the 301 response into a complete forged 200 | line 69 (`response`) | `evidence/ev_r12_U_6fb186ed_d5.txt` `evidence/ev_r12_U_ctl_6fb186ed.txt` `evidence/ev_r12_U_6fb186ed_d6.txt` |

## Findings

### SEC-001 — Decoded CRLF in a directory name splits the 301 response into a complete forged 200

Same sink as 8d5ff1f2: the 301 Location is concatenated from the decoded path with no re-check, so a directory name carrying CRLF and a full status line yields two responses in one client stream, including the attacker body. The decoder at line 62 rejects only NUL and backslash, while the config validator on the same build rejects bytes below 32.

Evidence: `evidence/ev_r12_U_6fb186ed_d5.txt` `evidence/ev_r12_U_ctl_6fb186ed.txt` `evidence/ev_r12_U_6fb186ed_d6.txt`

## Artifact index

- `evidence/ev_r12_U_6fb186ed_d5.txt`
- `evidence/ev_r12_U_ctl_6fb186ed.txt`
- `evidence/ev_r12_U_6fb186ed_d6.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
