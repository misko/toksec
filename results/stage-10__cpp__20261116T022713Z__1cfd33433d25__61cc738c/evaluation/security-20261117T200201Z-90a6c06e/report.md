# Security audit — run 61cc738c — release/000001 (round 8, lane H)

Connection state as the authority: the keepalive counter versus the location that configured it,
the idle deadline versus `keepalive_timeout`, and (on the pooled build) a one-byte `MSG_PEEK`
liveness check. Release source read from the tag and byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; the proxy executes nothing.

## Audit narrative

Control first on the same config, with a byte-identical control/payload treated as a no-op. The
matrix then walked the counter across two locations with different `keepalive_requests`, idled a
connection past a configured 2s `keepalive_timeout`, and pipelined two requests in one packet. On
the pooled build the peer was made to dribble bytes to straddle the peek window; the peer log
proves every request really reached it, so a substituted body is a proxy defect and not a dropped
request.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A proxied response always closes, so a pipelined static request behind it is eaten | line 68 (`proxy(`) | `evidence/ev_r8_H_61c_proxy_then_static.txt` |

## Findings

### SEC-001 — A proxied response always closes, so a pipelined static request behind it is eaten

serve() calls proxy(io,r,*loc,path,q,true,pending) with the close flag hardcoded true on the proxied branch, so every proxied response is written Connection: close and the connection ends without draining a pipelined tail. Two requests in one packet, the first proxied, returns only the first. Precondition: a proxied location and a pipelined packet.

Evidence: `evidence/ev_r8_H_61c_proxy_then_static.txt`, `evidence/ev_r8_H_61c_proxyclose.txt`

## Artifact index

- `evidence/ev_r8_H_61c_proxy_then_static.txt`
- `evidence/ev_r8_H_61c_proxyclose.txt`
