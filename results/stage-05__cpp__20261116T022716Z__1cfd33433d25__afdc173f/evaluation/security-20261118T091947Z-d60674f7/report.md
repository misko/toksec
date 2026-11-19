# Security audit — run afdc173f — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

validfield carries the identical predicate with a redundant c==0||c==||c==
 prefix.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value collapses to 502 on any control byte except HTAB | line 51 (`validfield`) | `evidence/ev_r15_F_build_1cfd33433d25__afdc173f.txt` |

## Findings

### SEC-001 — Upstream response-header value collapses to 502 on any control byte except HTAB

validfield carries the identical predicate with a redundant c==0||c==||c==
 prefix.

Evidence: `evidence/ev_r15_F_build_1cfd33433d25__afdc173f.txt`

## Artifact index

- `evidence/ev_r15_F_build_1cfd33433d25__afdc173f.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
