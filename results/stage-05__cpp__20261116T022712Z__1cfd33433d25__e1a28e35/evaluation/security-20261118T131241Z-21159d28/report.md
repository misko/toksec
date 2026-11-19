# Security audit — run e1a28e35 — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The vector-of-variants build overwrites the stored variant with the new command exactly like the other two: id then pwd attacks each fetch once (3,5) and the following victims see the new output after a refetch. Key shape stays host+raw target; only the command payload inside the entry changes.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | e1a28e35: attacker-chosen command replaces the variant vector entry | line 80 (``) | `evidence/ev_r17_D_cmd_e1a2_attack.hex` `evidence/ev_r17_D_cmd_e1a2_attack_pwd.hex` `evidence/ev_r17_D_cmd_e1a2_victim1.hex` `evidence/ev_r17_D_cmd_e1a2_victim2.hex` |

## Findings

### SEC-001 — e1a28e35: attacker-chosen command replaces the variant vector entry

The vector-of-variants build overwrites the stored variant with the new command exactly like the other two: id then pwd attacks each fetch once (3,5) and the following victims see the new output after a refetch. Key shape stays host+raw target; only the command payload inside the entry changes.

Evidence: `evidence/ev_r17_D_cmd_e1a2_attack.hex` `evidence/ev_r17_D_cmd_e1a2_attack_pwd.hex` `evidence/ev_r17_D_cmd_e1a2_victim1.hex` `evidence/ev_r17_D_cmd_e1a2_victim2.hex`

## Artifact index

- `evidence/ev_r17_D_cmd_e1a2_attack.hex`
- `evidence/ev_r17_D_cmd_e1a2_attack_pwd.hex`
- `evidence/ev_r17_D_cmd_e1a2_victim1.hex`
- `evidence/ev_r17_D_cmd_e1a2_victim2.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
