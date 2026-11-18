# Security audit — run 6baf — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

safe_header rejects CR, LF and NUL at parse time and the same predicate gates emission, so the build agrees with itself. The strongest of the six builds in this lane and the reference point for the others.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Parse and emit share one restrictive predicate, so no malformed head escapes; eleven of fifteen modes refused | line 68 (`safe_header`) | `evidence/ev_r12_V_6baf_predicate.txt` `evidence/ev_r12_V_6baf_clShort.txt` |

## Findings

### SEC-001 — Parse and emit share one restrictive predicate, so no malformed head escapes; eleven of fifteen modes refused

safe_header rejects CR, LF and NUL at parse time and the same predicate gates emission, so the build agrees with itself. The strongest of the six builds in this lane and the reference point for the others.

Evidence: `evidence/ev_r12_V_6baf_predicate.txt` `evidence/ev_r12_V_6baf_clShort.txt`

## Artifact index

- `evidence/ev_r12_V_6baf_predicate.txt`
- `evidence/ev_r12_V_6baf_clShort.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
