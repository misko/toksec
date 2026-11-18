# Security audit — run e1a28e35 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The vector-of-variants build matches the wildcard builds: the gzip victim after an identity-AE poison is served at zero fetches, and a no-AE attacker's overwrite (stored with vary=false because the peer sends no Vary) is then served to the next no-AE victim at zero fetches.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | e1a28e35: variant vector also serves cross-AE victims at zero fetch | line 79 (``) | `evidence/ev_r17_D_xae_e1a2_vgzip.hex` `evidence/ev_r17_D_xae_e1a2_attacknoae.hex` `evidence/ev_r17_D_xae_e1a2_vnoae.hex` |

## Findings

### SEC-001 — e1a28e35: variant vector also serves cross-AE victims at zero fetch

The vector-of-variants build matches the wildcard builds: the gzip victim after an identity-AE poison is served at zero fetches, and a no-AE attacker's overwrite (stored with vary=false because the peer sends no Vary) is then served to the next no-AE victim at zero fetches.

Evidence: `evidence/ev_r17_D_xae_e1a2_vgzip.hex` `evidence/ev_r17_D_xae_e1a2_attacknoae.hex` `evidence/ev_r17_D_xae_e1a2_vnoae.hex`

## Artifact index

- `evidence/ev_r17_D_xae_e1a2_vgzip.hex`
- `evidence/ev_r17_D_xae_e1a2_attacknoae.hex`
- `evidence/ev_r17_D_xae_e1a2_vnoae.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
