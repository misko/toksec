# Security audit — run 61cc738c — release/000001 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The 301 Location is built from the decoded path after pathnorm at line 63 accepted control bytes; the injected block closes the real header block, so the client receives a complete second response with a body. On this build a POST carrying any non-zero Content-Length is a 400, so all shapes are GET.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Decoded CRLF in a directory name splits the 301 response into a complete forged 200 | line 66 (`Location`) | `evidence/ev_r12_U_61cc738c_d5.txt` `evidence/ev_r12_U_ctl_61cc738c.txt` `evidence/ev_r12_U_61cc738c_d6.txt` |

## Findings

### SEC-001 — Decoded CRLF in a directory name splits the 301 response into a complete forged 200

The 301 Location is built from the decoded path after pathnorm at line 63 accepted control bytes; the injected block closes the real header block, so the client receives a complete second response with a body. On this build a POST carrying any non-zero Content-Length is a 400, so all shapes are GET.

Evidence: `evidence/ev_r12_U_61cc738c_d5.txt` `evidence/ev_r12_U_ctl_61cc738c.txt` `evidence/ev_r12_U_61cc738c_d6.txt`

## Artifact index

- `evidence/ev_r12_U_61cc738c_d5.txt`
- `evidence/ev_r12_U_ctl_61cc738c.txt`
- `evidence/ev_r12_U_61cc738c_d6.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
