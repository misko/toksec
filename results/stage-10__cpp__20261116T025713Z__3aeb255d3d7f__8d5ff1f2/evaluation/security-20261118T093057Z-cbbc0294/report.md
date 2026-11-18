# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same sink as the single-hop finding, reached from another build's output rather than from a client.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Hop 2 of the chain executes the decoded split it is handed | line 89 (`proxy_request`) | `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex` |

## Findings

### SEC-001 — Hop 2 of the chain executes the decoded split it is handed

Same sink as the single-hop finding, reached from another build's output rather than from a client.

Evidence: `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex`

## Artifact index

- `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
