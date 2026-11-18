# Security audit — run 8d5ff1f2 — release/000002 (round 8, lane H)

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
| SEC-001 | yes | low | keepalive_requests is compared against a counter shared by every location on the connection, so a low-limit location closes the connection for a different one | line 87 (`keepreq`) | `evidence/ev_r8_H_8d5_kr1.log` |
| SEC-002 | yes | low | keepalive_timeout is parsed into keepsec and never read; the real idle deadline is a hardcoded 75 seconds | line 96 (`c.last`) | `evidence/ev_r8_H_8d5_idle.log` |
| SEC-003 | yes | low | A pipelined second request is eaten when the first response closes the connection | line 87 (`keepreq`) | `evidence/ev_r8_H_8d5_eats_pipeline.txt` |

## Findings

### SEC-001 — keepalive_requests is compared against a counter shared by every location on the connection, so a low-limit location closes the connection for a different one

close is computed as ++c.count>=loc->s.keepreq where c.count lives on the Client and the limit comes from whichever location this request resolved to. Visiting /one/ (keepalive_requests 1) and then a /two/ request on the same connection still sees count reach the low limit and closes, and vice versa a high-limit location lets the counter run past a sibling's configured limit. One request is enough to observe: after the counter meets the low limit the response carries Connection: close. Precondition: two locations with different keepalive_requests.

Evidence: `evidence/ev_r8_H_8d5_kr1.log`, `evidence/ev_r8_H_8d5_shared3.log`, `evidence/ev_r8_H_8d5_krhuge.log`

### SEC-002 — keepalive_timeout is parsed into keepsec and never read; the real idle deadline is a hardcoded 75 seconds

apply() stores keepalive_timeout into s.keepsec and the close expression consults it only through !loc->s.keepsec (zero vs non-zero), never as a duration. The enforced idle deadline is the literal if(time(nullptr)-c.last>75) in the poll loop, so a configured keepalive_timeout 2s still leaves the socket alive for 75s and a configured large value does not extend past 75s. Precondition: none beyond a keepalive connection.

Evidence: `evidence/ev_r8_H_8d5_idle.log`

### SEC-003 — A pipelined second request is eaten when the first response closes the connection

The close decision is taken before the pipelined tail is processed, and the processed tail is only re-run after the write completes and only when close is false. Sending two requests in one packet where the first hits a keepalive_requests 1 location returns only the first response; the second is dropped with no error to the client. Precondition: a low keepalive_requests location and a pipelined packet.

Evidence: `evidence/ev_r8_H_8d5_eats_pipeline.txt`, `evidence/ev_r8_H_8d5_pipe1.log`

## Artifact index

- `evidence/ev_r8_H_8d5_kr1.log`
- `evidence/ev_r8_H_8d5_shared3.log`
- `evidence/ev_r8_H_8d5_krhuge.log`
- `evidence/ev_r8_H_8d5_idle.log`
- `evidence/ev_r8_H_8d5_eats_pipeline.txt`
- `evidence/ev_r8_H_8d5_pipe1.log`
