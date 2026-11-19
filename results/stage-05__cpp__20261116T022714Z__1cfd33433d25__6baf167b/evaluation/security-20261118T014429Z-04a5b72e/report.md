# Security audit — run 6baf — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

rd.ensure(n) demands the full declared length, so the client never sees a short body under a big length. The contrast with the 61cc738c row is exact: one build refuses, one ships the lie.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | A short body under a large Content-Length is refused with 502 rather than shipped as a mismatch | line 99 (`ensure`) | `evidence/ev_r12_V_6baf_clShort.txt` |

## Findings

### SEC-001 — A short body under a large Content-Length is refused with 502 rather than shipped as a mismatch

rd.ensure(n) demands the full declared length, so the client never sees a short body under a big length. The contrast with the 61cc738c row is exact: one build refuses, one ships the lie.

Evidence: `evidence/ev_r12_V_6baf_clShort.txt`

## Artifact index

- `evidence/ev_r12_V_6baf_clShort.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
