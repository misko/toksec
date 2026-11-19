# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

With cache_bytes=200000, each filler /api/x?vN? fetches once and is cached; after six fillers the original /api/x?<smug> victim fetches upstream again (hit 10, captured upstream line proves the miss) and after twelve it misses again (hit 16). The poison survives only while it is the sole or least-recently-used entry; persistence across real traffic pressure is negative on all four builds.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Poison does not survive ordinary cache pressure: six distinct targets evict it | line 73 (``) | `evidence/ev_r17_D_evict_a4ba_d0.hex` `evidence/ev_r17_D_evict_a4ba_victim6.hex` `evidence/ev_r17_D_evict_a4ba_victim12.hex` `evidence/ev_r17_D_evict_a4ba_up_victim.hex` |

## Findings

### SEC-001 — Poison does not survive ordinary cache pressure: six distinct targets evict it

With cache_bytes=200000, each filler /api/x?vN? fetches once and is cached; after six fillers the original /api/x?<smug> victim fetches upstream again (hit 10, captured upstream line proves the miss) and after twelve it misses again (hit 16). The poison survives only while it is the sole or least-recently-used entry; persistence across real traffic pressure is negative on all four builds.

Evidence: `evidence/ev_r17_D_evict_a4ba_d0.hex` `evidence/ev_r17_D_evict_a4ba_victim6.hex` `evidence/ev_r17_D_evict_a4ba_victim12.hex` `evidence/ev_r17_D_evict_a4ba_up_victim.hex`

## Artifact index

- `evidence/ev_r17_D_evict_a4ba_d0.hex`
- `evidence/ev_r17_D_evict_a4ba_victim6.hex`
- `evidence/ev_r17_D_evict_a4ba_victim12.hex`
- `evidence/ev_r17_D_evict_a4ba_up_victim.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
