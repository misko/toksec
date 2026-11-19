# Security audit — run e1a28e35 — release/000002 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Both runs return `HTTP/1.1 400 Bad Request`, `Content-Length: 0`, `Connection: close` at 5.01 s. The 5 s is this build's socket timeout, so the client waits its full deadline and then learns the request failed, with no interim frame in between.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A waiting client is answered with a bare `400` after 5 s instead of any `100` | line 84 (`hop.count`) | `evidence/ev_r11_R_ste1a28e35.st.txt` |

## Findings

### SEC-001 — A waiting client is answered with a bare `400` after 5 s instead of any `100`

Both runs return `HTTP/1.1 400 Bad Request`, `Content-Length: 0`, `Connection: close` at 5.01 s. The 5 s is this build's socket timeout, so the client waits its full deadline and then learns the request failed, with no interim frame in between.

Evidence: `evidence/ev_r11_R_ste1a28e35.st.txt`

## Artifact index

- `evidence/ev_r11_R_ste1a28e35.st.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
