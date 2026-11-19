# Security audit — run 44bf — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

proxy_simple excludes only the built-in names and never appends a body, so both the deletion shape and the unframed-body shape are structurally unavailable.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Fixed strip list; client tokens ignored and no body is ever forwarded | line 87 (`k!=`) | `evidence/ev_r12_W_44bf7f35_sem.log` `evidence/ev_r12_W_44bf7f35_poc.log` |

## Findings

### SEC-001 — Fixed strip list; client tokens ignored and no body is ever forwarded

proxy_simple excludes only the built-in names and never appends a body, so both the deletion shape and the unframed-body shape are structurally unavailable.

Evidence: `evidence/ev_r12_W_44bf7f35_sem.log` `evidence/ev_r12_W_44bf7f35_poc.log`

## Artifact index

- `evidence/ev_r12_W_44bf7f35_sem.log`
- `evidence/ev_r12_W_44bf7f35_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
