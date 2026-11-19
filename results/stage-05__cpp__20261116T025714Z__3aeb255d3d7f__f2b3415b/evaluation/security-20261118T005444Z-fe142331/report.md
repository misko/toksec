# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same on the per-client guard: chunked framing changes nothing because the guard inspects the method. One attempt, 502, body lost on failover. Confirms there is no chunked bypass to the one-attempt branch.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A chunked POST does not escape the GET/HEAD-only failover guard | line 86 (`upfail`) | `evidence/ev_r12_X_ev_f2b_chunkedpost.txt` `evidence/ev_r12_X_ev_f2b_chunkedget.txt` |

## Findings

### SEC-001 — A chunked POST does not escape the GET/HEAD-only failover guard

Same on the per-client guard: chunked framing changes nothing because the guard inspects the method. One attempt, 502, body lost on failover. Confirms there is no chunked bypass to the one-attempt branch.

Evidence: `evidence/ev_r12_X_ev_f2b_chunkedpost.txt` `evidence/ev_r12_X_ev_f2b_chunkedget.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_chunkedpost.txt`
- `evidence/ev_r12_X_ev_f2b_chunkedget.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
