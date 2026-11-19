# Security audit — run 29d05850 — release/000002 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Failed upstream kills connection with no retry and no cross-request buffer reuse.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Negative: clean epoll pipeline semantics on 29d05850 | line 56 (`failup`) | `evidence/ev_r13_C_29d.headfail.client.hex` `evidence/ev_r13_C_29d.pipe_ctl.u2.hex` `evidence/ev_r13_C_29d.pipe_headfail.client.hex` |

## Findings

### SEC-001 — Negative: clean epoll pipeline semantics on 29d05850

Failed upstream kills connection with no retry and no cross-request buffer reuse.

Evidence: `evidence/ev_r13_C_29d.headfail.client.hex` `evidence/ev_r13_C_29d.pipe_ctl.u2.hex` `evidence/ev_r13_C_29d.pipe_headfail.client.hex`

## Artifact index

- `evidence/ev_r13_C_29d.headfail.client.hex`
- `evidence/ev_r13_C_29d.pipe_ctl.u2.hex`
- `evidence/ev_r13_C_29d.pipe_headfail.client.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
