# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

After the identity-AE attack, a victim with Accept-Encoding: gzip is served the poisoned entry at zero new fetches (captured upstream count stays at 4; the hit body is the identity LINE with EXEC:0 because this run's overwrite came from a clean earlier fetch of the same raw target). Re-attack without any Accept-Encoding header stores under base|* (enc() is empty), and the following no-AE victim is then served at zero fetches, confirming the store-side wildcard arm is reachable from a no-AE attacker too. 6baf167b refetches on both cross-AE victims, which is exactly its intended negative contrast.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Wildcard arm confirmed at zero fetch: gzip and no-AE victims are served the identity-AE poison; no-AE attack stores under |* | line 72 (``) | `evidence/ev_r17_D_xae_a4ba_vgzip.hex` `evidence/ev_r17_D_xae_a4ba_up_vgzip.hex` `evidence/ev_r17_D_xae_a4ba_attacknoae.hex` `evidence/ev_r17_D_xae_a4ba_vnoae.hex` |

## Findings

### SEC-001 — Wildcard arm confirmed at zero fetch: gzip and no-AE victims are served the identity-AE poison; no-AE attack stores under |*

After the identity-AE attack, a victim with Accept-Encoding: gzip is served the poisoned entry at zero new fetches (captured upstream count stays at 4; the hit body is the identity LINE with EXEC:0 because this run's overwrite came from a clean earlier fetch of the same raw target). Re-attack without any Accept-Encoding header stores under base|* (enc() is empty), and the following no-AE victim is then served at zero fetches, confirming the store-side wildcard arm is reachable from a no-AE attacker too. 6baf167b refetches on both cross-AE victims, which is exactly its intended negative contrast.

Evidence: `evidence/ev_r17_D_xae_a4ba_vgzip.hex` `evidence/ev_r17_D_xae_a4ba_up_vgzip.hex` `evidence/ev_r17_D_xae_a4ba_attacknoae.hex` `evidence/ev_r17_D_xae_a4ba_vnoae.hex`

## Artifact index

- `evidence/ev_r17_D_xae_a4ba_vgzip.hex`
- `evidence/ev_r17_D_xae_a4ba_up_vgzip.hex`
- `evidence/ev_r17_D_xae_a4ba_attacknoae.hex`
- `evidence/ev_r17_D_xae_a4ba_vnoae.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
