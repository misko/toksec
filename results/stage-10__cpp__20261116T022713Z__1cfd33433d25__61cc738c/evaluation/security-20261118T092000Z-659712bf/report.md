# Security audit — run 61cc738c — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The body reader does not stop at the first response boundary, so the second response reaches the client.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A whole second response after the terminator is leaked to the client | line 67 (`proxy`) | `evidence/ev_r15_G_61cc_tesecond.log` |

## Findings

### SEC-001 — A whole second response after the terminator is leaked to the client

The body reader does not stop at the first response boundary, so the second response reaches the client.

Evidence: `evidence/ev_r15_G_61cc_tesecond.log`

## Artifact index

- `evidence/ev_r15_G_61cc_tesecond.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
