# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

upfail() advances c->attempt and re-enters startup() for a GET/HEAD on the first failure, which rebuilds and re-sends from the parsed request. When the first upstream executed and then died, the second upstream executes the same split command. Retry is a single fixed hop, not a budget: with three upstreams the third is never dialled.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The per-client failover guard retries a request whose command already ran, executing it twice | line 86 (`upfail`) | `evidence/ev_r12_X_ev_f2b_execfail.txt` `evidence/ev_r12_X_ev_f2b_close.txt` `evidence/ev_r12_X_ev_f2b_control.txt` |

## Findings

### SEC-001 — The per-client failover guard retries a request whose command already ran, executing it twice

upfail() advances c->attempt and re-enters startup() for a GET/HEAD on the first failure, which rebuilds and re-sends from the parsed request. When the first upstream executed and then died, the second upstream executes the same split command. Retry is a single fixed hop, not a budget: with three upstreams the third is never dialled.

Evidence: `evidence/ev_r12_X_ev_f2b_execfail.txt` `evidence/ev_r12_X_ev_f2b_close.txt` `evidence/ev_r12_X_ev_f2b_control.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_execfail.txt`
- `evidence/ev_r12_X_ev_f2b_close.txt`
- `evidence/ev_r12_X_ev_f2b_control.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
