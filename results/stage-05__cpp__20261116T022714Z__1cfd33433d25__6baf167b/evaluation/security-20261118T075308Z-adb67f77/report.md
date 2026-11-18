# Security audit — run 6baf167b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(strips `Authorization`) Same shape and control. Upstream head
`GET //f.txt HTTP/1.1\r\nHost: 127.0.0.1:48132\r\nContent-Length: 0\r\nConnection: keep-alive` — no
`authorization` (`ev_r14_A_6baf167b_v2.log`, index 4).
Source line: **line 94 (`hop`)** — `for(auto&x:tokens(val(h,"connection")))s.insert(x);`.
Precondition: same as §7. Evidence: `ev_r14_A_6baf167b_v2.log`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `auth_del` — 6baf167b hop | line 94 (`hop`) | `evidence/ev_r14_A_6baf167b_v2.log` |

## Findings

### SEC-001 — negative for `auth_del` — 6baf167b hop

(strips `Authorization`) Same shape and control. Upstream head
`GET //f.txt HTTP/1.1\r\nHost: 127.0.0.1:48132\r\nContent-Length: 0\r\nConnection: keep-alive` — no
`authorization` (`ev_r14_A_6baf167b_v2.log`, index 4).
Source line: **line 94 (`hop`)** — `for(auto&x:tokens(val(h,"connection")))s.insert(x);`.
Precondition: same as §7. Evidence: `ev_r14_A_6baf167b_v2.log`.

Evidence: `evidence/ev_r14_A_6baf167b_v2.log`

## Artifact index

- `evidence/ev_r14_A_6baf167b_v2.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
