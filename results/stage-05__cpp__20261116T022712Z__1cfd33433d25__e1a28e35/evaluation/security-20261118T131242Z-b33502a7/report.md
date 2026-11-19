# Security audit — run e1a28e35 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

HEAD hits at zero fetch with the poisoned Content-Length, Range is ignored and the full body is served at 200, If-None-Match is ignored, POST refetches. Method is not in the key here either.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | e1a28e35: same conditional behavior on the variant-vector entry | line 79 (``) | `evidence/ev_r17_D_cond_e1a2_head.hex` `evidence/ev_r17_D_cond_e1a2_range.hex` `evidence/ev_r17_D_cond_e1a2_inm.hex` `evidence/ev_r17_D_cond_e1a2_post.hex` |

## Findings

### SEC-001 — e1a28e35: same conditional behavior on the variant-vector entry

HEAD hits at zero fetch with the poisoned Content-Length, Range is ignored and the full body is served at 200, If-None-Match is ignored, POST refetches. Method is not in the key here either.

Evidence: `evidence/ev_r17_D_cond_e1a2_head.hex` `evidence/ev_r17_D_cond_e1a2_range.hex` `evidence/ev_r17_D_cond_e1a2_inm.hex` `evidence/ev_r17_D_cond_e1a2_post.hex`

## Artifact index

- `evidence/ev_r17_D_cond_e1a2_head.hex`
- `evidence/ev_r17_D_cond_e1a2_range.hex`
- `evidence/ev_r17_D_cond_e1a2_inm.hex`
- `evidence/ev_r17_D_cond_e1a2_post.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
