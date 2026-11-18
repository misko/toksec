# Security audit — run 6baf167b — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`Expect` is forwarded but never honoured, and `status<200` makes a `100 Continue` abort the exchange into a flat `502`. The client's request body — a whole `GET /api%2fexec%20?cmd=uname%20-a` line, sent with `Content-Length: 0` on the outer POST — is then re-parsed as the next request, decoded and executed upstream. One client request returns two heads (`502` then `200` with `SEQ:2 EXEC:uid=1000`), 6/6 deterministic, and the effect survives a non-exec isolation POST so the `uid` output cannot come from request 1. Precondition: a proxy location plus an upstream that actually emits `100 Continue`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The upstream's interim `100` is rejected as a parse failure, and the leftover request body is re-parsed as a second request that executes | line 97 (`r.h`) | `evidence/ev_r11_R_6baf.iso.txt` `evidence/ev_r11_R_6baf.rep.txt` |

## Findings

### SEC-001 — The upstream's interim `100` is rejected as a parse failure, and the leftover request body is re-parsed as a second request that executes

`Expect` is forwarded but never honoured, and `status<200` makes a `100 Continue` abort the exchange into a flat `502`. The client's request body — a whole `GET /api%2fexec%20?cmd=uname%20-a` line, sent with `Content-Length: 0` on the outer POST — is then re-parsed as the next request, decoded and executed upstream. One client request returns two heads (`502` then `200` with `SEQ:2 EXEC:uid=1000`), 6/6 deterministic, and the effect survives a non-exec isolation POST so the `uid` output cannot come from request 1. Precondition: a proxy location plus an upstream that actually emits `100 Continue`.

Evidence: `evidence/ev_r11_R_6baf.iso.txt` `evidence/ev_r11_R_6baf.rep.txt`

## Artifact index

- `evidence/ev_r11_R_6baf.iso.txt`
- `evidence/ev_r11_R_6baf.rep.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
