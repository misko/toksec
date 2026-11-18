# Security audit — run 6fb186ed — release/000004 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

decodepath at 62 has no <32 arm, so the decoded separator survives. On stock nginx the /exec suffix is still an anchored exec route and the command runs, with the 0.9 reply surfacing as 502 to the caller. Node returns 400 so the shape is consumer-dependent.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Third armed decoder; extensionless anchor plus a passed control byte executes on stock nginx | line 62 (`decodepath`) | `evidence/ev_r16_A_cap_6fb186ed_exec09crlf.log` `evidence/ev_r16_A_final_6fb186ed.txt` |

## Findings

### SEC-001 — Third armed decoder; extensionless anchor plus a passed control byte executes on stock nginx

decodepath at 62 has no <32 arm, so the decoded separator survives. On stock nginx the /exec suffix is still an anchored exec route and the command runs, with the 0.9 reply surfacing as 502 to the caller. Node returns 400 so the shape is consumer-dependent.

Evidence: `evidence/ev_r16_A_cap_6fb186ed_exec09crlf.log` `evidence/ev_r16_A_final_6fb186ed.txt`

## Artifact index

- `evidence/ev_r16_A_cap_6fb186ed_exec09crlf.log`
- `evidence/ev_r16_A_final_6fb186ed.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
