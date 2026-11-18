# Security audit — run afdc173f — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same result as the level-5 build: victim misses after six and again after twelve distinct fillers, so the wildcard entry has no special persistence. LRU-by-insertion-sequence eviction at line 78 treats the poisoned entry like any other.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | afdc173f: identical eviction behavior under the same pressure | line 78 (``) | `evidence/ev_r17_D_evict_afdc_victim6.hex` `evidence/ev_r17_D_evict_afdc_victim12.hex` |

## Findings

### SEC-001 — afdc173f: identical eviction behavior under the same pressure

Same result as the level-5 build: victim misses after six and again after twelve distinct fillers, so the wildcard entry has no special persistence. LRU-by-insertion-sequence eviction at line 78 treats the poisoned entry like any other.

Evidence: `evidence/ev_r17_D_evict_afdc_victim6.hex` `evidence/ev_r17_D_evict_afdc_victim12.hex`

## Artifact index

- `evidence/ev_r17_D_evict_afdc_victim6.hex`
- `evidence/ev_r17_D_evict_afdc_victim12.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
