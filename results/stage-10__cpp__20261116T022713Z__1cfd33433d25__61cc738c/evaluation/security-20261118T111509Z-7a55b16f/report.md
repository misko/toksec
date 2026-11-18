# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

61cc738c rejects only c==0 and c==backslash, so exec09 with a CRLF or LF yields the same 0.9 demotion and blind execution. Both real consumers accept the shape and demote; the client is told 502 while the command has run. It also pins its whole process during slowloris because hdeadline is parsed and never read.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Same armed decoder: decoded control byte survives into the upstream line and executes blind on stock nginx and python | line 63 (`pathnorm`) | `evidence/ev_r16_A_cap_61cc738c_exec09crlf.log` `evidence/ev_r16_A_final_61cc738c.txt` |

## Findings

### SEC-001 — Same armed decoder: decoded control byte survives into the upstream line and executes blind on stock nginx and python

61cc738c rejects only c==0 and c==backslash, so exec09 with a CRLF or LF yields the same 0.9 demotion and blind execution. Both real consumers accept the shape and demote; the client is told 502 while the command has run. It also pins its whole process during slowloris because hdeadline is parsed and never read.

Evidence: `evidence/ev_r16_A_cap_61cc738c_exec09crlf.log` `evidence/ev_r16_A_final_61cc738c.txt`

## Artifact index

- `evidence/ev_r16_A_cap_61cc738c_exec09crlf.log`
- `evidence/ev_r16_A_final_61cc738c.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
