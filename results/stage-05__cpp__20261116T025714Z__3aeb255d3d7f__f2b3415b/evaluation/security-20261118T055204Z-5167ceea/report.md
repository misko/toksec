# Security audit — run f2b3415b — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Retry resets upin/upout per attempt; no buffer carry-over observed under head-fail and body-fail controls.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Negative: clean retry semantics on f2b3415b | line 85 (`startup`) | `evidence/ev_r13_C_f2b.headfail.client.hex` `evidence/ev_r13_C_f2b.headfail.u2.hex` `evidence/ev_r13_C_f2b.pipe_headfail.client.hex` |

## Findings

### SEC-001 — Negative: clean retry semantics on f2b3415b

Retry resets upin/upout per attempt; no buffer carry-over observed under head-fail and body-fail controls.

Evidence: `evidence/ev_r13_C_f2b.headfail.client.hex` `evidence/ev_r13_C_f2b.headfail.u2.hex` `evidence/ev_r13_C_f2b.pipe_headfail.client.hex`

## Artifact index

- `evidence/ev_r13_C_f2b.headfail.client.hex`
- `evidence/ev_r13_C_f2b.headfail.u2.hex`
- `evidence/ev_r13_C_f2b.pipe_headfail.client.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
