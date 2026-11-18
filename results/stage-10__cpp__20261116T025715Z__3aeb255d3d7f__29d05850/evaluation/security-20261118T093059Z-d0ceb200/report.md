# Security audit — run 29d05850 — release/000002 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

3/3 pairs identical on this build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | TLS parity: upstream request bytes identical over TLS and plaintext | line 50 (`request`) | `evidence/ev_r15_E_t29db_upstream_parity.hex` |

## Findings

### SEC-001 — TLS parity: upstream request bytes identical over TLS and plaintext

3/3 pairs identical on this build.

Evidence: `evidence/ev_r15_E_t29db_upstream_parity.hex`

## Artifact index

- `evidence/ev_r15_E_t29db_upstream_parity.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
