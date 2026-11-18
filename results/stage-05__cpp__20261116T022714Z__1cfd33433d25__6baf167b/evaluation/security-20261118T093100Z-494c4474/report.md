# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Negative: the witness must be in the path, not the query.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A query-only split keeps %0d%0a literal and does not execute | line 62 (`decodepath`) | `evidence/ev_r15_E_queryonly_6b_upstream.hex` |

## Findings

### SEC-001 — A query-only split keeps %0d%0a literal and does not execute

Negative: the witness must be in the path, not the query.

Evidence: `evidence/ev_r15_E_queryonly_6b_upstream.hex`

## Artifact index

- `evidence/ev_r15_E_queryonly_6b_upstream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
