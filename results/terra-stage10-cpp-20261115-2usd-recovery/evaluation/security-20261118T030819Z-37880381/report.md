# Security audit — run 2usd — release/000007 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

proxyfetch ignores the client list entirely and sends HTTP/1.0 with Connection: close and no Content-Length; all five probed headers forwarded unchanged and POST is 405.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The recovery build forwards a fixed HTTP/1.0 request with no client-controlled deletion and no body path | line 78 (`proxyfetch`) | `evidence/ev_r12_W_2usd_sem.log` `evidence/ev_r12_W_2usd_poc.log` |

## Findings

### SEC-001 — The recovery build forwards a fixed HTTP/1.0 request with no client-controlled deletion and no body path

proxyfetch ignores the client list entirely and sends HTTP/1.0 with Connection: close and no Content-Length; all five probed headers forwarded unchanged and POST is 405.

Evidence: `evidence/ev_r12_W_2usd_sem.log` `evidence/ev_r12_W_2usd_poc.log`

## Artifact index

- `evidence/ev_r12_W_2usd_sem.log`
- `evidence/ev_r12_W_2usd_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
