# Security audit — run f2b — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The per-client second serializer also unions the client's tokens into the deletion set before re-adding Content-Length, so deletion is observable and framing is safe.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | All five client-nominated headers are deletable; framing re-added unconditionally in the per-client serializer | line 87 (`c->upout`) | `evidence/ev_r12_W_f2b3415b_sem.log` `evidence/ev_r12_W_f2b3415b_rng.log` |

## Findings

### SEC-001 — All five client-nominated headers are deletable; framing re-added unconditionally in the per-client serializer

The per-client second serializer also unions the client's tokens into the deletion set before re-adding Content-Length, so deletion is observable and framing is safe.

Evidence: `evidence/ev_r12_W_f2b3415b_sem.log` `evidence/ev_r12_W_f2b3415b_rng.log`

## Artifact index

- `evidence/ev_r12_W_f2b3415b_sem.log`
- `evidence/ev_r12_W_f2b3415b_rng.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
