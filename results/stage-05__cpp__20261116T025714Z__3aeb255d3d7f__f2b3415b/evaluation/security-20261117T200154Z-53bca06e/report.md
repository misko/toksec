# Security audit — run f2b3415b — release/000001 (round 8, lane H)

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
| SEC-001 | yes | medium | Pool liveness is one MSG_PEEK byte, so an upstream byte arriving in the peek-to-send window makes the next client receive the previous client's response | line 87 (`MSG_PEEK`) | `evidence/ev_r8_H_f2b_poison2.txt` |
| SEC-002 | yes | low | max_requests is enforced on a per-connection counter but the pool ignores Host, so a bound reached on one vhost retires a socket another vhost is using | line 73 (`maxreq`) | `evidence/ev_r8_H_f2b_bound.log` |
| SEC-003 | yes | low | A stray upstream byte in the peek window turns the next request into a 502 instead of a substituted body | line 87 (`MSG_PEEK`) | `evidence/ev_r8_H_f2b_straybyte.txt` |

## Findings

### SEC-001 — Pool liveness is one MSG_PEEK byte, so an upstream byte arriving in the peek-to-send window makes the next client receive the previous client's response

startup() pops a pooled fd and treats a single recv(fd,&x,1,MSG_PEEK|MSG_DONTWAIT) returning >=0 as proof the socket is idle, then reuses it for the new request. An upstream that writes its response slowly straddles that check: the peek sees the first byte of a still-live response, the proxy still sends the new request on the same socket, and the parser reads the old response as the answer. Result is either a 502 mid-stream or a full response belonging to another client, with the peer log proving both requests were really served. Precondition: pooled upstream reuse and a slow upstream.

Evidence: `evidence/ev_r8_H_f2b_poison2.txt`, `evidence/ev_r8_H_f2b_peekrace_hit.txt`, `evidence/ev_r8_H_f2b_peek.log`

### SEC-002 — max_requests is enforced on a per-connection counter but the pool ignores Host, so a bound reached on one vhost retires a socket another vhost is using

respond() increments the connection request counter and compares it against cfg.maxreq; the pool index comes from a global round-robin with no Host component, so requests for different host_root values land on the same pooled fd and share that counter. A burst on one vhost therefore ends the keep-alive of a connection another vhost believes is its own. Precondition: pooled reuse with more than one vhost.

Evidence: `evidence/ev_r8_H_f2b_bound.log`, `evidence/ev_r8_H_f2b_crossvhost.log`

### SEC-003 — A stray upstream byte in the peek window turns the next request into a 502 instead of a substituted body

Same window, other outcome: when only part of a header arrives, the peek succeeds but the new request's response parse starts mid-header, and responseparse fails the client with 502 rather than reuse. Precondition: pooled reuse and an upstream that dribbles bytes.

Evidence: `evidence/ev_r8_H_f2b_straybyte.txt`, `evidence/ev_r8_H_f2b_delay2.log`

## Artifact index

- `evidence/ev_r8_H_f2b_poison2.txt`
- `evidence/ev_r8_H_f2b_peekrace_hit.txt`
- `evidence/ev_r8_H_f2b_peek.log`
- `evidence/ev_r8_H_f2b_bound.log`
- `evidence/ev_r8_H_f2b_crossvhost.log`
- `evidence/ev_r8_H_f2b_straybyte.txt`
- `evidence/ev_r8_H_f2b_delay2.log`
