# Security audit — run 44bf7f35 — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same CL skip applied recursively: upstream got three connections and executed twice (POST /api/, then GET /api/exec?cmd=id, then the nested body as a third request). Client got three responses, LEN 472.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | A nested inner Content-Length replays twice, yielding two executions from one send | line 87 (`proxy_simple`) | `evidence/ev_r15_G_44bf_precl.log` |

## Findings

### SEC-001 — A nested inner Content-Length replays twice, yielding two executions from one send

Same CL skip applied recursively: upstream got three connections and executed twice (POST /api/, then GET /api/exec?cmd=id, then the nested body as a third request). Client got three responses, LEN 472.

Evidence: `evidence/ev_r15_G_44bf_precl.log`

## Artifact index

- `evidence/ev_r15_G_44bf_precl.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
