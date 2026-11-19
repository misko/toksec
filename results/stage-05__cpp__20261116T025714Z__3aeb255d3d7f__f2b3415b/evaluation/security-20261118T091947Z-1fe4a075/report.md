# Security audit — run f2b3415b — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

validvalue carries the identical predicate, the fifth character-for-character copy.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value collapses to 502 on any control byte except HTAB | line 55 (`validvalue`) | `evidence/ev_r15_F_build_3aeb255d3d7f__f2b3415b.txt` |

## Findings

### SEC-001 — Upstream response-header value collapses to 502 on any control byte except HTAB

validvalue carries the identical predicate, the fifth character-for-character copy.

Evidence: `evidence/ev_r15_F_build_3aeb255d3d7f__f2b3415b.txt`

## Artifact index

- `evidence/ev_r15_F_build_3aeb255d3d7f__f2b3415b.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
