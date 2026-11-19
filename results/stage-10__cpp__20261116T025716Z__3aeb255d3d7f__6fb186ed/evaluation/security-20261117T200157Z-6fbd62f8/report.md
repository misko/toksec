# Security audit — run 6fb186ed — release/000004 (round 8, lane H)

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
| SEC-001 | yes | low | The connection keep-alive bound is a hardcoded 1000 and the per-location keepalive_requests directive is dead | line 66 (`requests`) | `evidence/ev_r8_H_6fb_bound.log` |

## Findings

### SEC-001 — The connection keep-alive bound is a hardcoded 1000 and the per-location keepalive_requests directive is dead

The location parse stores keepalive_requests into l.keepalive_requests, but the request path closes on ++c.requests>=1000 regardless of the location's value, so keepalive_requests 1 behaves like 1000 and 10000 is capped at 1000. Observed by driving 1001 requests on one connection: the 1000th responds Connection: close. Precondition: none.

Evidence: `evidence/ev_r8_H_6fb_bound.log`, `evidence/ev_r8_H_6fb_1000.log`

## Artifact index

- `evidence/ev_r8_H_6fb_bound.log`
- `evidence/ev_r8_H_6fb_1000.log`
