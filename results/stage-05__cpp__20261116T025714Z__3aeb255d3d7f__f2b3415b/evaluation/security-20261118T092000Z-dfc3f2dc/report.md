# Security audit — run f2b3415b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The leftover-bytes check fails the exchange instead of relaying, closing with 502.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A whole second response after the terminator gives a 502 | line 89 (`used!=s.size()`) | `evidence/ev_r15_G_f2b_tesecond.log` |

## Findings

### SEC-001 — A whole second response after the terminator gives a 502

The leftover-bytes check fails the exchange instead of relaying, closing with 502.

Evidence: `evidence/ev_r15_G_f2b_tesecond.log`

## Artifact index

- `evidence/ev_r15_G_f2b_tesecond.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
