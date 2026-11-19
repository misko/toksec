# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

fail-first on both configured peers exhausts the one permitted retry and the request 502s even with a healthy third upstream configured and reachable.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Retry is a single hop rather than a budget, so a third upstream is never dialled | line 80 (`attempt`) | `evidence/ev_r12_X_ev_afdc_3ups.txt` |

## Findings

### SEC-001 — Retry is a single hop rather than a budget, so a third upstream is never dialled

fail-first on both configured peers exhausts the one permitted retry and the request 502s even with a healthy third upstream configured and reachable.

Evidence: `evidence/ev_r12_X_ev_afdc_3ups.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_3ups.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
