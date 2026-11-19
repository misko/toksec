# Security audit — run afdc173f — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same sequence as a4ba: gzip victim after identity-AE poison is a zero-fetch cache hit, and a no-AE attacker also lands in base|* so the following no-AE victim is served at zero fetches. This is the widening that 6baf167b lacks.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | afdc173f: wildcard arm serves cross-AE victims at zero fetch, including a no-AE attacker | line 77 (``) | `evidence/ev_r17_D_xae_afdc_vgzip.hex` `evidence/ev_r17_D_xae_afdc_attacknoae.hex` `evidence/ev_r17_D_xae_afdc_vnoae.hex` |

## Findings

### SEC-001 — afdc173f: wildcard arm serves cross-AE victims at zero fetch, including a no-AE attacker

Same sequence as a4ba: gzip victim after identity-AE poison is a zero-fetch cache hit, and a no-AE attacker also lands in base|* so the following no-AE victim is served at zero fetches. This is the widening that 6baf167b lacks.

Evidence: `evidence/ev_r17_D_xae_afdc_vgzip.hex` `evidence/ev_r17_D_xae_afdc_attacknoae.hex` `evidence/ev_r17_D_xae_afdc_vnoae.hex`

## Artifact index

- `evidence/ev_r17_D_xae_afdc_vgzip.hex`
- `evidence/ev_r17_D_xae_afdc_attacknoae.hex`
- `evidence/ev_r17_D_xae_afdc_vnoae.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
