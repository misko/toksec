# Security audit — run afdc173f — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

HEAD hits with zero fetch and poisoned Content-Length, Range returns the full body at 200 with zero fetch, fabricated If-None-Match is ignored and the full 200 poison is served, POST refetches. Identical depth semantics to the level-5 build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | afdc173f: same conditional behavior on the wildcard entry | line 77 (``) | `evidence/ev_r17_D_cond_afdc_head.hex` `evidence/ev_r17_D_cond_afdc_range.hex` `evidence/ev_r17_D_cond_afdc_inm.hex` `evidence/ev_r17_D_cond_afdc_post.hex` |

## Findings

### SEC-001 — afdc173f: same conditional behavior on the wildcard entry

HEAD hits with zero fetch and poisoned Content-Length, Range returns the full body at 200 with zero fetch, fabricated If-None-Match is ignored and the full 200 poison is served, POST refetches. Identical depth semantics to the level-5 build.

Evidence: `evidence/ev_r17_D_cond_afdc_head.hex` `evidence/ev_r17_D_cond_afdc_range.hex` `evidence/ev_r17_D_cond_afdc_inm.hex` `evidence/ev_r17_D_cond_afdc_post.hex`

## Artifact index

- `evidence/ev_r17_D_cond_afdc_head.hex`
- `evidence/ev_r17_D_cond_afdc_range.hex`
- `evidence/ev_r17_D_cond_afdc_inm.hex`
- `evidence/ev_r17_D_cond_afdc_post.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
