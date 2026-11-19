# Security audit — run ae021893 — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same copy-pasted predicate as the other four truncating builds; the value is judged per byte after the block was cut, never as a delimiter.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value collapses to 502 on any control byte except HTAB | line 64 (`upstream`) | `evidence/ev_r15_F_build_3aeb255d3d7f__ae021893.txt` |

## Findings

### SEC-001 — Upstream response-header value collapses to 502 on any control byte except HTAB

Same copy-pasted predicate as the other four truncating builds; the value is judged per byte after the block was cut, never as a delimiter.

Evidence: `evidence/ev_r15_F_build_3aeb255d3d7f__ae021893.txt`

## Artifact index

- `evidence/ev_r15_F_build_3aeb255d3d7f__ae021893.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
