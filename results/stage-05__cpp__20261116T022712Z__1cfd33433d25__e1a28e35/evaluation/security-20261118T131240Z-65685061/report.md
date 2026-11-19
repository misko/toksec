# Security audit — run e1a28e35 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

e1a28e35 keeps a vector of Accept-Encoding variants per raw-target key and matches on stored vary/AE pairs, but the key itself is again host+raw target: /api?x, /api/?x and /?x refetch, /?x serves the local static file. No prefix-root poisoning is possible here either.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | e1a28e35 confirms the same key width with per-key variant vectors | line 85 (``) | `evidence/ev_r17_D_root_e1a2_apiq.hex` `evidence/ev_r17_D_root_e1a2_apixq.hex` `evidence/ev_r17_D_root_e1a2_slashq.hex` |

## Findings

### SEC-001 — e1a28e35 confirms the same key width with per-key variant vectors

e1a28e35 keeps a vector of Accept-Encoding variants per raw-target key and matches on stored vary/AE pairs, but the key itself is again host+raw target: /api?x, /api/?x and /?x refetch, /?x serves the local static file. No prefix-root poisoning is possible here either.

Evidence: `evidence/ev_r17_D_root_e1a2_apiq.hex` `evidence/ev_r17_D_root_e1a2_apixq.hex` `evidence/ev_r17_D_root_e1a2_slashq.hex`

## Artifact index

- `evidence/ev_r17_D_root_e1a2_apiq.hex`
- `evidence/ev_r17_D_root_e1a2_apixq.hex`
- `evidence/ev_r17_D_root_e1a2_slashq.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
