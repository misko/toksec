# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

c->attempt is cleared on every dispatch into startup(), which makes the per-request budget explicit rather than incidental. Measured as 2+2+2 over three pipelined GETs; a chunked POST pipelined ahead of a GET still left the GET two full attempts.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The per-client attempt counter is reset before each proxied dispatch, so pipelining is safe | line 95 (`startup`) | `evidence/ev_r12_X_ev_f2b_pipe3_execfail.txt` |

## Findings

### SEC-001 — The per-client attempt counter is reset before each proxied dispatch, so pipelining is safe

c->attempt is cleared on every dispatch into startup(), which makes the per-request budget explicit rather than incidental. Measured as 2+2+2 over three pipelined GETs; a chunked POST pipelined ahead of a GET still left the GET two full attempts.

Evidence: `evidence/ev_r12_X_ev_f2b_pipe3_execfail.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_pipe3_execfail.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
