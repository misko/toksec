# Security audit — run f2b3415b — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Confirms the per-client serializer is not the source of any divergence: identity holds across all four failure modes with only Host differing.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The second serializer also rebuilds from the decoded path and is byte-identical to attempt 1 | line 87 (`req.path.substr`) | `evidence/ev_r12_X_ev_f2b_close.txt` `evidence/ev_r12_X_ev_f2b_hdrstrip.txt` |

## Findings

### SEC-001 — The second serializer also rebuilds from the decoded path and is byte-identical to attempt 1

Confirms the per-client serializer is not the source of any divergence: identity holds across all four failure modes with only Host differing.

Evidence: `evidence/ev_r12_X_ev_f2b_close.txt` `evidence/ev_r12_X_ev_f2b_hdrstrip.txt`

## Artifact index

- `evidence/ev_r12_X_ev_f2b_close.txt`
- `evidence/ev_r12_X_ev_f2b_hdrstrip.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
