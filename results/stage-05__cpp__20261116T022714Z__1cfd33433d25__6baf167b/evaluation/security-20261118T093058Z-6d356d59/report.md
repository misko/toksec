# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Six-variant matrix: identical bytes hit, trailing slash misses, Authorization bypasses, other Host misses, uppercase %2F misses. Scope is narrow and predictable, which is what makes the critical reliable rather than flaky.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Cache key is host+raw target, so poison scope is exactly one target and case-sensitive | line 89 (`cached`) | `evidence/ev_r15_E_kc_matrix.txt` |

## Findings

### SEC-001 — Cache key is host+raw target, so poison scope is exactly one target and case-sensitive

Six-variant matrix: identical bytes hit, trailing slash misses, Authorization bypasses, other Host misses, uppercase %2F misses. Scope is narrow and predictable, which is what makes the critical reliable rather than flaky.

Evidence: `evidence/ev_r15_E_kc_matrix.txt`

## Artifact index

- `evidence/ev_r15_E_kc_matrix.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
