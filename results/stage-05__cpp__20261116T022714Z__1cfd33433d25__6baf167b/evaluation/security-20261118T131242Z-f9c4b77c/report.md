# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

After the identity-AE poison, a gzip victim fetches upstream again (hit 4), and a no-AE attack stores a second distinct entry (hit 5) so the no-AE victim hits that one at zero fetches (hit 6). Key is host+target+'\n'+AE with no wildcard arm, exactly the built-in negative this round was asked to contrast against.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Negative contrast: 6baf167b refetches for both cross-AE victims and stores the no-AE attack under its own key | line 88 (``) | `evidence/ev_r17_D_xae_6baf_vgzip.hex` `evidence/ev_r17_D_xae_6baf_attacknoae.hex` `evidence/ev_r17_D_xae_6baf_vnoae.hex` |

## Findings

### SEC-001 — Negative contrast: 6baf167b refetches for both cross-AE victims and stores the no-AE attack under its own key

After the identity-AE poison, a gzip victim fetches upstream again (hit 4), and a no-AE attack stores a second distinct entry (hit 5) so the no-AE victim hits that one at zero fetches (hit 6). Key is host+target+'\n'+AE with no wildcard arm, exactly the built-in negative this round was asked to contrast against.

Evidence: `evidence/ev_r17_D_xae_6baf_vgzip.hex` `evidence/ev_r17_D_xae_6baf_attacknoae.hex` `evidence/ev_r17_D_xae_6baf_vnoae.hex`

## Artifact index

- `evidence/ev_r17_D_xae_6baf_vgzip.hex`
- `evidence/ev_r17_D_xae_6baf_attacknoae.hex`
- `evidence/ev_r17_D_xae_6baf_vnoae.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
