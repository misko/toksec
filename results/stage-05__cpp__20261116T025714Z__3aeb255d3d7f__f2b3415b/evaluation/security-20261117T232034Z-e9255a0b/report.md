# Security audit — run f2b3415b — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Both runs return `HTTP/1.1 400 Bad Request`, `Content-Length: 0`, `Connection: close` at 2.00 s. The status is generic, so the client cannot tell an expectation mismatch from a malformed request.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A waiting client is answered with a bare `400` after 2 s | line 88 (`status<200`) | `evidence/ev_r11_R_stf2b3415b.st.txt` |

## Findings

### SEC-001 — A waiting client is answered with a bare `400` after 2 s

Both runs return `HTTP/1.1 400 Bad Request`, `Content-Length: 0`, `Connection: close` at 2.00 s. The status is generic, so the client cannot tell an expectation mismatch from a malformed request.

Evidence: `evidence/ev_r11_R_stf2b3415b.st.txt`

## Artifact index

- `evidence/ev_r11_R_stf2b3415b.st.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
