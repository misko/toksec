# Security audit — run 44bf7f35 — release/000001 (round 11, lane A2)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Precondition matrix cell `unframed_exec` driven and captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | unframed/replayed body executes on the upstream | line 87 (`proxy_simple`) | `evidence/ev_r15_A2_44bf7f35_unframed_exec.log` |

## Findings

### SEC-001 — unframed/replayed body executes on the upstream

Round-15 completion of the RCE-precondition matrix. `unframed_exec` driven control-first on the final tag, upstream request bytes captured in hex. Execution (where present) is on the upstream host.

Evidence: `evidence/ev_r15_A2_44bf7f35_unframed_exec.log`

## Artifact index

- `evidence/ev_r15_A2_44bf7f35_unframed_exec.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
