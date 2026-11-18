# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The exact-key build misses at the same points under the same pressure, so persistence is a property of the cache sizes, not of the wildcard arm.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Negative contrast: 6baf167b evicts identically, confirming this is not wildcard-specific | line 88 (``) | `evidence/ev_r17_D_evict_6baf_victim6.hex` `evidence/ev_r17_D_evict_6baf_victim12.hex` |

## Findings

### SEC-001 — Negative contrast: 6baf167b evicts identically, confirming this is not wildcard-specific

The exact-key build misses at the same points under the same pressure, so persistence is a property of the cache sizes, not of the wildcard arm.

Evidence: `evidence/ev_r17_D_evict_6baf_victim6.hex` `evidence/ev_r17_D_evict_6baf_victim12.hex`

## Artifact index

- `evidence/ev_r17_D_evict_6baf_victim6.hex`
- `evidence/ev_r17_D_evict_6baf_victim12.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
