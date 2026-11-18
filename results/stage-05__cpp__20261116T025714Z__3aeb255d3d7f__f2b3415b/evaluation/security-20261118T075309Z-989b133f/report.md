# Security audit — run f2b3415b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(strips `Authorization`) Same shape and control. Upstream head
`GET //f.txt HTTP/1.1\r\nHost: 127.0.0.1:48134\r\nContent-Length: 0\r\nConnection: keep-alive` — no
`authorization` (`ev_r14_A_f2b3415b_v2.log`, index 4).
Source line: **line 84 (`hopset`)** — `auto t=tokens(geth(h,"connection"));s.insert(t.begin(),t.end());`.
Precondition: same as §7. Evidence: `ev_r14_A_f2b3415b_v2.log`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `auth_del` — f2b3415b hopset | line 84 (`hopset`) | `evidence/ev_r14_A_f2b3415b_v2.log` |

## Findings

### SEC-001 — negative for `auth_del` — f2b3415b hopset

(strips `Authorization`) Same shape and control. Upstream head
`GET //f.txt HTTP/1.1\r\nHost: 127.0.0.1:48134\r\nContent-Length: 0\r\nConnection: keep-alive` — no
`authorization` (`ev_r14_A_f2b3415b_v2.log`, index 4).
Source line: **line 84 (`hopset`)** — `auto t=tokens(geth(h,"connection"));s.insert(t.begin(),t.end());`.
Precondition: same as §7. Evidence: `ev_r14_A_f2b3415b_v2.log`.

Evidence: `evidence/ev_r14_A_f2b3415b_v2.log`

## Artifact index

- `evidence/ev_r14_A_f2b3415b_v2.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
