# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Hop 1 decodes the double-encoded target and hands hop 2 a line hop 2 itself parses. Hop 2's egress is byte-identical to the single-hop shape and executes. First proven chain in the corpus.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Two-hop chain: a caching decoder in front of a second proxy delivers the split to a real executing upstream | line 62 (`decodepath`) | `evidence/ev_r15_E_chain_hop1_6baf167b_egress.hex` `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex` |

## Findings

### SEC-001 — Two-hop chain: a caching decoder in front of a second proxy delivers the split to a real executing upstream

Hop 1 decodes the double-encoded target and hands hop 2 a line hop 2 itself parses. Hop 2's egress is byte-identical to the single-hop shape and executes. First proven chain in the corpus.

Evidence: `evidence/ev_r15_E_chain_hop1_6baf167b_egress.hex` `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex`

## Artifact index

- `evidence/ev_r15_E_chain_hop1_6baf167b_egress.hex`
- `evidence/ev_r15_E_chain_hop2_8d5ff1f2_upstream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
