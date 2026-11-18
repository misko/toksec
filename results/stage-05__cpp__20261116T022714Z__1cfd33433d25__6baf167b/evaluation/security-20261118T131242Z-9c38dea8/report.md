# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

HEAD, Range and If-None-Match all serve the exact-key poison at zero fetches and POST refetches, matching the wildcard builds. Conditional-path behavior is therefore generic to this cache family and not a wildcard-only amplification.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Negative contrast: 6baf167b shows the same conditional depth on its exact key | line 88 (``) | `evidence/ev_r17_D_cond_6baf_head.hex` `evidence/ev_r17_D_cond_6baf_range.hex` `evidence/ev_r17_D_cond_6baf_inm.hex` `evidence/ev_r17_D_cond_6baf_post.hex` |

## Findings

### SEC-001 — Negative contrast: 6baf167b shows the same conditional depth on its exact key

HEAD, Range and If-None-Match all serve the exact-key poison at zero fetches and POST refetches, matching the wildcard builds. Conditional-path behavior is therefore generic to this cache family and not a wildcard-only amplification.

Evidence: `evidence/ev_r17_D_cond_6baf_head.hex` `evidence/ev_r17_D_cond_6baf_range.hex` `evidence/ev_r17_D_cond_6baf_inm.hex` `evidence/ev_r17_D_cond_6baf_post.hex`

## Artifact index

- `evidence/ev_r17_D_cond_6baf_head.hex`
- `evidence/ev_r17_D_cond_6baf_range.hex`
- `evidence/ev_r17_D_cond_6baf_inm.hex`
- `evidence/ev_r17_D_cond_6baf_post.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
