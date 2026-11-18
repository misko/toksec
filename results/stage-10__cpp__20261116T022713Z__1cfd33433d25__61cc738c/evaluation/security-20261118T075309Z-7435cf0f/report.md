# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(decoded CRLF left raw in the request line)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | desync — 61cc738c pathnorm | line 63 (`pathnorm`) | `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_refnginx2_plain.log` |

## Findings

### SEC-001 — desync — 61cc738c pathnorm

(decoded CRLF left raw in the request line)

Evidence: `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_refnginx2_plain.log`

## Artifact index

- `evidence/ev_r14_A_61cc738c_v2.log`
- `evidence/ev_r14_A_61cc738c_v2_out.log`
- `evidence/ev_r14_A_refnginx2_plain.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
