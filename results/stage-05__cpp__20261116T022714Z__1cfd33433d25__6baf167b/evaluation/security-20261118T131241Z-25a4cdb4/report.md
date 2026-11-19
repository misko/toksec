# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The exact-key build shows the same overwrite behavior with attacker-chosen commands, confirming that command choice in the entry is generic to these caches and that the wildcard builds' extra reach (cross-AE victim) is the only divergence, not the overwrite mechanism itself.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Negative contrast: 6baf167b also overwrites on the exact key, no wildcard involved | line 88 (``) | `evidence/ev_r17_D_cmd_6baf_attack.hex` `evidence/ev_r17_D_cmd_6baf_attack_pwd.hex` `evidence/ev_r17_D_cmd_6baf_victim1.hex` `evidence/ev_r17_D_cmd_6baf_victim2.hex` |

## Findings

### SEC-001 — Negative contrast: 6baf167b also overwrites on the exact key, no wildcard involved

The exact-key build shows the same overwrite behavior with attacker-chosen commands, confirming that command choice in the entry is generic to these caches and that the wildcard builds' extra reach (cross-AE victim) is the only divergence, not the overwrite mechanism itself.

Evidence: `evidence/ev_r17_D_cmd_6baf_attack.hex` `evidence/ev_r17_D_cmd_6baf_attack_pwd.hex` `evidence/ev_r17_D_cmd_6baf_victim1.hex` `evidence/ev_r17_D_cmd_6baf_victim2.hex`

## Artifact index

- `evidence/ev_r17_D_cmd_6baf_attack.hex`
- `evidence/ev_r17_D_cmd_6baf_attack_pwd.hex`
- `evidence/ev_r17_D_cmd_6baf_victim1.hex`
- `evidence/ev_r17_D_cmd_6baf_victim2.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
