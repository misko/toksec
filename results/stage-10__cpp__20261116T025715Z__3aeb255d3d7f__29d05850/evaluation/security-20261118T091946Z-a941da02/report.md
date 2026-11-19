# Security audit — run 29d05850 — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The only fully verbatim sink found: 32/32 control bytes and DEL reach the client unchanged; HTAB is eaten by trim() at the value edge only. No predicate exists on this build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value is relayed verbatim; only edge HTAB is absorbed | line 57 (`trim`) | `evidence/ev_r15_F_build_3aeb255d3d7f__29d05850.txt` |

## Findings

### SEC-001 — Upstream response-header value is relayed verbatim; only edge HTAB is absorbed

The only fully verbatim sink found: 32/32 control bytes and DEL reach the client unchanged; HTAB is eaten by trim() at the value edge only. No predicate exists on this build.

Evidence: `evidence/ev_r15_F_build_3aeb255d3d7f__29d05850.txt`

## Artifact index

- `evidence/ev_r15_F_build_3aeb255d3d7f__29d05850.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
