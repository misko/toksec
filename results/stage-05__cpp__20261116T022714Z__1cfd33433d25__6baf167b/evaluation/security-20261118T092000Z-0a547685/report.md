# Security audit — run 6baf167b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Buffered read stops at the framed length, second response discarded.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A whole second response after the terminator is dropped by the client | line 99 (`rd.ensure`) | `evidence/ev_r15_G_6baf_tesecond.log` |

## Findings

### SEC-001 — A whole second response after the terminator is dropped by the client

Buffered read stops at the framed length, second response discarded.

Evidence: `evidence/ev_r15_G_6baf_tesecond.log`

## Artifact index

- `evidence/ev_r15_G_6baf_tesecond.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
