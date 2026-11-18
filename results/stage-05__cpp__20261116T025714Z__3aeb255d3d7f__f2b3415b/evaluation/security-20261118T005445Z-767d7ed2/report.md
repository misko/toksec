# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The second serializer rebuilds Content-Length from the already de-chunked body, so attempt 1 and attempt 2 agree on the length and the bytes; only Host differs. Chunk splitting inside the target does not destabilise the replay.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | A chunked GET replays its de-chunked body byte-identically on retry | line 87 (`req.path.substr`) | `evidence/ev_r12_X_ev_f2b_chunkedget.txt` |

## Findings

### SEC-001 — A chunked GET replays its de-chunked body byte-identically on retry

The second serializer rebuilds Content-Length from the already de-chunked body, so attempt 1 and attempt 2 agree on the length and the bytes; only Host differs. Chunk splitting inside the target does not destabilise the replay.

Evidence: `evidence/ev_r12_X_ev_f2b_chunkedget.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_chunkedget.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
