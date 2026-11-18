# Security audit — run e1a28e35 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Victim misses after six and after twelve fillers exactly like the other builds; the per-key variant vector does not change eviction priority.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | e1a28e35: identical eviction behavior under the same pressure | line 80 (``) | `evidence/ev_r17_D_evict_e1a2_victim6.hex` `evidence/ev_r17_D_evict_e1a2_victim12.hex` |

## Findings

### SEC-001 — e1a28e35: identical eviction behavior under the same pressure

Victim misses after six and after twelve fillers exactly like the other builds; the per-key variant vector does not change eviction priority.

Evidence: `evidence/ev_r17_D_evict_e1a2_victim6.hex` `evidence/ev_r17_D_evict_e1a2_victim12.hex`

## Artifact index

- `evidence/ev_r17_D_evict_e1a2_victim6.hex`
- `evidence/ev_r17_D_evict_e1a2_victim12.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
