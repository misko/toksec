# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Successive identity-AE attacks on the same raw target with cmd=id, cmd=pwd and cmd=uname each fetch upstream once (hit counts 3,5,6) and overwrite the same cache entry; the captured upstream lines show the attacker-chosen command inside the smuggled second request. The next victim to the same target always refetches after an overwrite, then serves the new command output from cache on subsequent hits, so the attacker chooses what the next victims execute without touching them.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Attacker-chosen command is embedded in the cached entry and each overwrite retargets later victims | line 73 (``) | `evidence/ev_r17_D_cmd_a4ba_attack_id.hex` `evidence/ev_r17_D_cmd_a4ba_attack_pwd.hex` `evidence/ev_r17_D_cmd_a4ba_up_pwd.hex` `evidence/ev_r17_D_cmd_a4ba_up_uname.hex` |

## Findings

### SEC-001 — Attacker-chosen command is embedded in the cached entry and each overwrite retargets later victims

Successive identity-AE attacks on the same raw target with cmd=id, cmd=pwd and cmd=uname each fetch upstream once (hit counts 3,5,6) and overwrite the same cache entry; the captured upstream lines show the attacker-chosen command inside the smuggled second request. The next victim to the same target always refetches after an overwrite, then serves the new command output from cache on subsequent hits, so the attacker chooses what the next victims execute without touching them.

Evidence: `evidence/ev_r17_D_cmd_a4ba_attack_id.hex` `evidence/ev_r17_D_cmd_a4ba_attack_pwd.hex` `evidence/ev_r17_D_cmd_a4ba_up_pwd.hex` `evidence/ev_r17_D_cmd_a4ba_up_uname.hex`

## Artifact index

- `evidence/ev_r17_D_cmd_a4ba_attack_id.hex`
- `evidence/ev_r17_D_cmd_a4ba_attack_pwd.hex`
- `evidence/ev_r17_D_cmd_a4ba_up_pwd.hex`
- `evidence/ev_r17_D_cmd_a4ba_up_uname.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
