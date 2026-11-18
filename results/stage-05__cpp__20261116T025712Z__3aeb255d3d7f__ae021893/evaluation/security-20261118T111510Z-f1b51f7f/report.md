# Security audit — run ae021893 — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

No shape executes on any stock consumer. The double slash the decoder emits defeats the .exec$ anchor, so even the shape that works on three sibling builds only produces 404s on nginx and 200s that are not exec on node/python. Executes only against the hand-written peer.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Worst stock-consumer parity in the corpus: the exec route is unreachable at every shape | line 51 (`parseheader`) | `evidence/ev_r16_A_final_ae021893.txt` `evidence/ev_r16_A_matrix.txt` |

## Findings

### SEC-001 — Worst stock-consumer parity in the corpus: the exec route is unreachable at every shape

No shape executes on any stock consumer. The double slash the decoder emits defeats the .exec$ anchor, so even the shape that works on three sibling builds only produces 404s on nginx and 200s that are not exec on node/python. Executes only against the hand-written peer.

Evidence: `evidence/ev_r16_A_final_ae021893.txt` `evidence/ev_r16_A_matrix.txt`

## Artifact index

- `evidence/ev_r16_A_final_ae021893.txt`
- `evidence/ev_r16_A_matrix.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
