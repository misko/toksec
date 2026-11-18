# Security audit — run f2b3415b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Second build of the pair. f2b3415b:88 requires Content-Length or Transfer-Encoding on the reply and 502s a reply that has neither. Invisible to the attacker as a status difference but it is why node looks like a proxy fault rather than a consumer decision.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Same hard-502 on an unframed upstream reply; node s valid 400 surfaces to the client as 502 | line 88 (`responseparse`) | `evidence/ev_r16_A_final_f2b3415b.txt` `evidence/ev_r16_A_matrix.txt` |

## Findings

### SEC-001 — Same hard-502 on an unframed upstream reply; node s valid 400 surfaces to the client as 502

Second build of the pair. f2b3415b:88 requires Content-Length or Transfer-Encoding on the reply and 502s a reply that has neither. Invisible to the attacker as a status difference but it is why node looks like a proxy fault rather than a consumer decision.

Evidence: `evidence/ev_r16_A_final_f2b3415b.txt` `evidence/ev_r16_A_matrix.txt`

## Artifact index

- `evidence/ev_r16_A_final_f2b3415b.txt`
- `evidence/ev_r16_A_matrix.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
