# Security audit — run afdc173f — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Pooled sockets never re-offered with residual bytes; retry buffer cleared per attempt.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Negative: clean pooled-socket retry on afdc173f | line 40 (`proxy`) | `evidence/ev_r13_C_afdc.headfail.u2.hex` `evidence/ev_r13_C_afdc.pool_headfail.client.hex` `evidence/ev_r13_C_afdc.pipe_headfail.client.hex` |

## Findings

### SEC-001 — Negative: clean pooled-socket retry on afdc173f

Pooled sockets never re-offered with residual bytes; retry buffer cleared per attempt.

Evidence: `evidence/ev_r13_C_afdc.headfail.u2.hex` `evidence/ev_r13_C_afdc.pool_headfail.client.hex` `evidence/ev_r13_C_afdc.pipe_headfail.client.hex`

## Artifact index

- `evidence/ev_r13_C_afdc.headfail.u2.hex`
- `evidence/ev_r13_C_afdc.pool_headfail.client.hex`
- `evidence/ev_r13_C_afdc.pipe_headfail.client.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
