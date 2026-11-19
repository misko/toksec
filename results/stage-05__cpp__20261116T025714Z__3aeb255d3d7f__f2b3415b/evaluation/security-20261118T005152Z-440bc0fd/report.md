# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The guard tests the method explicitly, so POST gets exactly one attempt and its body-carried second request is lost on upstream failure. Same client-visible result as afdc173f: 502 with a healthy peer available.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | The failover guard admits only GET and HEAD, so a POST body is never replayed | line 86 (`upfail`) | `evidence/ev_r12_X_ev_f2b_post.txt` |

## Findings

### SEC-001 — The failover guard admits only GET and HEAD, so a POST body is never replayed

The guard tests the method explicitly, so POST gets exactly one attempt and its body-carried second request is lost on upstream failure. Same client-visible result as afdc173f: 502 with a healthy peer available.

Evidence: `evidence/ev_r12_X_ev_f2b_post.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_post.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
