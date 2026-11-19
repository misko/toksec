# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The attempt counter is loop-local, and three pipelined GETs against always-failing peers produced exactly six connections and six executions (2+2+2), never 2+1+0 or 2+3+2. No spent retry crosses a request boundary.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Retry budget is per-request, so pipelining neither leaks nor grants extra attempts | line 80 (`attempt`) | `evidence/ev_r12_X_ev_afdc_pipe3_execfail.txt` `evidence/ev_r12_X_ev_afdc_pipe_postget.txt` |

## Findings

### SEC-001 — Retry budget is per-request, so pipelining neither leaks nor grants extra attempts

The attempt counter is loop-local, and three pipelined GETs against always-failing peers produced exactly six connections and six executions (2+2+2), never 2+1+0 or 2+3+2. No spent retry crosses a request boundary.

Evidence: `evidence/ev_r12_X_ev_afdc_pipe3_execfail.txt` `evidence/ev_r12_X_ev_afdc_pipe_postget.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_pipe3_execfail.txt`
- `evidence/ev_r12_X_ev_afdc_pipe_postget.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
