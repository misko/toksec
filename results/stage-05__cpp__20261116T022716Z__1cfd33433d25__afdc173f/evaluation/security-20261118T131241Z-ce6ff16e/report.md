# Security audit — run afdc173f — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same id then pwd sequence: each attack fetches once (3,5), both overwrite the same base|* entry, and the first victim after each overwrite refetches while later victims are served from the overwritten entry. Attack-chosen command choice is therefore a property of the poisoned entry, not of the level-5 build only.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | afdc173f: attacker-chosen command overwrites the wildcard entry identically | line 78 (``) | `evidence/ev_r17_D_cmd_afdc_attack.hex` `evidence/ev_r17_D_cmd_afdc_attack_pwd.hex` `evidence/ev_r17_D_cmd_afdc_victim1.hex` `evidence/ev_r17_D_cmd_afdc_victim2.hex` |

## Findings

### SEC-001 — afdc173f: attacker-chosen command overwrites the wildcard entry identically

Same id then pwd sequence: each attack fetches once (3,5), both overwrite the same base|* entry, and the first victim after each overwrite refetches while later victims are served from the overwritten entry. Attack-chosen command choice is therefore a property of the poisoned entry, not of the level-5 build only.

Evidence: `evidence/ev_r17_D_cmd_afdc_attack.hex` `evidence/ev_r17_D_cmd_afdc_attack_pwd.hex` `evidence/ev_r17_D_cmd_afdc_victim1.hex` `evidence/ev_r17_D_cmd_afdc_victim2.hex`

## Artifact index

- `evidence/ev_r17_D_cmd_afdc_attack.hex`
- `evidence/ev_r17_D_cmd_afdc_attack_pwd.hex`
- `evidence/ev_r17_D_cmd_afdc_victim1.hex`
- `evidence/ev_r17_D_cmd_afdc_victim2.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
