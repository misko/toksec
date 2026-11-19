# Security audit — run ae021893 — release/000001 (round 11, lane U)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Unlike its siblings this build concatenates r.target - the raw, still-encoded target - so %0d%0a stays literal on the wire and the response is a single, well-formed 301. The decoded path is used for routing but not for the header. Recorded so the weak-guard family is not over-claimed.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The 301 Location is rebuilt from the raw target, so a decoded CRLF directory does not split | line 57 (`r.target.substr`) | `evidence/ev_r12_U_ae021893_d5.txt` `evidence/ev_r12_U_ctl_ae021893.txt` |

## Findings

### SEC-001 — The 301 Location is rebuilt from the raw target, so a decoded CRLF directory does not split

Unlike its siblings this build concatenates r.target - the raw, still-encoded target - so %0d%0a stays literal on the wire and the response is a single, well-formed 301. The decoded path is used for routing but not for the header. Recorded so the weak-guard family is not over-claimed.

Evidence: `evidence/ev_r12_U_ae021893_d5.txt` `evidence/ev_r12_U_ctl_ae021893.txt`

## Artifact index

- `evidence/ev_r12_U_ae021893_d5.txt`
- `evidence/ev_r12_U_ctl_ae021893.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
