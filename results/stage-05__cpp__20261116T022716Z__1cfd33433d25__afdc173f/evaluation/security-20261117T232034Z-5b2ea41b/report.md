# Security audit — run afdc173f — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Both runs return `HTTP/1.1 408 Request Timeout`, `Content-Length: 0`, `Connection: close` at 2.00 s — the most accurate of the five answers, since the proxy does wait for a body the `100` never invited, but the client still has no interim frame and must decide whether to send.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A waiting client is answered `408 Request Timeout` after 2 s | line 80 (`q.h`) | `evidence/ev_r11_R_stafdc173f.st.txt` |

## Findings

### SEC-001 — A waiting client is answered `408 Request Timeout` after 2 s

Both runs return `HTTP/1.1 408 Request Timeout`, `Content-Length: 0`, `Connection: close` at 2.00 s — the most accurate of the five answers, since the proxy does wait for a body the `100` never invited, but the client still has no interim frame and must decide whether to send.

Evidence: `evidence/ev_r11_R_stafdc173f.st.txt`

## Artifact index

- `evidence/ev_r11_R_stafdc173f.st.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
