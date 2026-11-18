# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The loop bound is one iteration for POST, so a POST whose body carries the second request line is never replayed. The upstream runs nothing on attempt 2 and the client gets 502 although the healthy peer was reachable. The healthy control returns 200, so the 502 is the missing retry rather than a harness fault.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | The retry guard excludes POST, so a body-carried exec is lost on failover and becomes a 502 | line 80 (`attempt`) | `evidence/ev_r12_X_ev_afdc_post.txt` `evidence/ev_r12_X_ev_afdc_postctl.txt` |

## Findings

### SEC-001 — The retry guard excludes POST, so a body-carried exec is lost on failover and becomes a 502

The loop bound is one iteration for POST, so a POST whose body carries the second request line is never replayed. The upstream runs nothing on attempt 2 and the client gets 502 although the healthy peer was reachable. The healthy control returns 200, so the 502 is the missing retry rather than a harness fault.

Evidence: `evidence/ev_r12_X_ev_afdc_post.txt` `evidence/ev_r12_X_ev_afdc_postctl.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_post.txt`
- `evidence/ev_r12_X_ev_afdc_postctl.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
