# Security audit — run ae021893 — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Independent build, same result: a victim gets the smuggled exec body on a benign path. Two builds make it a family, not a one-off.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | critical | Same cache-install primitive on a second, independent build | line 67 (`cachekey`) | `evidence/ev_r15_E_k5b_victim_client_stream.hex` |

## Findings

### SEC-001 — Same cache-install primitive on a second, independent build

Independent build, same result: a victim gets the smuggled exec body on a benign path. Two builds make it a family, not a one-off.

Evidence: `evidence/ev_r15_E_k5b_victim_client_stream.hex`

## Artifact index

- `evidence/ev_r15_E_k5b_victim_client_stream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
