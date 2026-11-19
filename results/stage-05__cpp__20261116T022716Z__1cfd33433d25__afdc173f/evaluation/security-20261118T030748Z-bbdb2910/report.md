# Security audit — run afd — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Client-controlled deletion over the union list with an unconditional re-add; same observable 304/206 to 200 changes as the other client-driven builds.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | All five client-nominated headers are deletable; framing re-added unconditionally | line 80 (`req`) | `evidence/ev_r12_W_afdc173f_sem.log` `evidence/ev_r12_W_afdc173f_rng.log` |

## Findings

### SEC-001 — All five client-nominated headers are deletable; framing re-added unconditionally

Client-controlled deletion over the union list with an unconditional re-add; same observable 304/206 to 200 changes as the other client-driven builds.

Evidence: `evidence/ev_r12_W_afdc173f_sem.log` `evidence/ev_r12_W_afdc173f_rng.log`

## Artifact index

- `evidence/ev_r12_W_afdc173f_sem.log`
- `evidence/ev_r12_W_afdc173f_rng.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
