# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

After poisoning, a GET victim is served from cache at zero fetches. A HEAD to the same target also hits with zero fetches and returns 200 with the poisoned Content-Length: 50 header and no body; a Range: bytes=0-1 GET hits with zero fetches and returns the full 50-byte poisoned body at 200 (no 206, no slicing); a fabricated If-None-Match also hits at zero fetches and serves the full 200 poison because the stored upstream headers carry no ETag for the local 304 path to compare. Only a POST refetches (hit 5), so method is not part of the key and HEAD widens the poison to HEAD consumers.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | HEAD and Range are served from the poisoned entry; 304 is unreachable; POST bypasses | line 72 (``) | `evidence/ev_r17_D_cond_a4ba_vget.hex` `evidence/ev_r17_D_cond_a4ba_head.hex` `evidence/ev_r17_D_cond_a4ba_range.hex` `evidence/ev_r17_D_cond_a4ba_post.hex` |

## Findings

### SEC-001 — HEAD and Range are served from the poisoned entry; 304 is unreachable; POST bypasses

After poisoning, a GET victim is served from cache at zero fetches. A HEAD to the same target also hits with zero fetches and returns 200 with the poisoned Content-Length: 50 header and no body; a Range: bytes=0-1 GET hits with zero fetches and returns the full 50-byte poisoned body at 200 (no 206, no slicing); a fabricated If-None-Match also hits at zero fetches and serves the full 200 poison because the stored upstream headers carry no ETag for the local 304 path to compare. Only a POST refetches (hit 5), so method is not part of the key and HEAD widens the poison to HEAD consumers.

Evidence: `evidence/ev_r17_D_cond_a4ba_vget.hex` `evidence/ev_r17_D_cond_a4ba_head.hex` `evidence/ev_r17_D_cond_a4ba_range.hex` `evidence/ev_r17_D_cond_a4ba_post.hex`

## Artifact index

- `evidence/ev_r17_D_cond_a4ba_vget.hex`
- `evidence/ev_r17_D_cond_a4ba_head.hex`
- `evidence/ev_r17_D_cond_a4ba_range.hex`
- `evidence/ev_r17_D_cond_a4ba_post.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
