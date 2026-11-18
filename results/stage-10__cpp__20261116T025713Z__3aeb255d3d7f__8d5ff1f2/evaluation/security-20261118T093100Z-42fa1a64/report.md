# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

TLS chain hop-2 upstream bytes are byte-identical to the same chain with hop 1 plaintext.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | A TLS front hop carries the chain exec to hop 2 unchanged | line 77 (`pathnorm`) | `evidence/ev_r15_E_tls_chain_hop2_upstream_tls.hex` |

## Findings

### SEC-001 — A TLS front hop carries the chain exec to hop 2 unchanged

TLS chain hop-2 upstream bytes are byte-identical to the same chain with hop 1 plaintext.

Evidence: `evidence/ev_r15_E_tls_chain_hop2_upstream_tls.hex`

## Artifact index

- `evidence/ev_r15_E_tls_chain_hop2_upstream_tls.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
