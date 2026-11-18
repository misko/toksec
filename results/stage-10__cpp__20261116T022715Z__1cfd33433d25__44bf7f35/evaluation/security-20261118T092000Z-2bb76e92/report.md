# Security audit — run 44bf7f35 — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The client sees only the first response; the surplus is discarded.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A whole second response after the terminator is dropped by the client | line 87 (`proxy_simple`) | `evidence/ev_r15_G_44bf_tesecond.log` |

## Findings

### SEC-001 — A whole second response after the terminator is dropped by the client

The client sees only the first response; the surplus is discarded.

Evidence: `evidence/ev_r15_G_44bf_tesecond.log`

## Artifact index

- `evidence/ev_r15_G_44bf_tesecond.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
