# Security audit — run ae021893 — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The status window rejects only outside 100-599, so the `100` becomes the client's response: `HTTP/1.1 100 Error`, `Content-Length: 0`, `Connection: keep-alive` (reason phrase is the generic `Error`). The body is still re-parsed and executed 2/2, so the client receives a success-shaped head with no body and cannot distinguish it from a real one. Same precondition as the other interim findings: a proxy location and a 100-emitting upstream.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | This build accepts 1xx as terminal, relays `100 Error` to the client as the whole response, and executes the body as a second request | line 64 (`hops.count`) | `evidence/ev_r11_R_ae02.iso.txt` `evidence/ev_r11_R_ae02.shift.txt` |

## Findings

### SEC-001 — This build accepts 1xx as terminal, relays `100 Error` to the client as the whole response, and executes the body as a second request

The status window rejects only outside 100-599, so the `100` becomes the client's response: `HTTP/1.1 100 Error`, `Content-Length: 0`, `Connection: keep-alive` (reason phrase is the generic `Error`). The body is still re-parsed and executed 2/2, so the client receives a success-shaped head with no body and cannot distinguish it from a real one. Same precondition as the other interim findings: a proxy location and a 100-emitting upstream.

Evidence: `evidence/ev_r11_R_ae02.iso.txt` `evidence/ev_r11_R_ae02.shift.txt`

## Artifact index

- `evidence/ev_r11_R_ae02.iso.txt`
- `evidence/ev_r11_R_ae02.shift.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
