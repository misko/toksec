# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Key is exactly host+raw target and the key is unchanged by the split, so the poisoned entry is served to any client asking for the attack's own target. Victim1 and victim2 each send identical benign bytes and both receive EXEC:1 with command output, at the attacker's HIT counter.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | critical | One attack request installs a cached EXEC body that a later benign client gets served | line 88 (`cachekey`) | `evidence/ev_r15_E_k3b_victim_client_stream.hex` |

## Findings

### SEC-001 — One attack request installs a cached EXEC body that a later benign client gets served

Key is exactly host+raw target and the key is unchanged by the split, so the poisoned entry is served to any client asking for the attack's own target. Victim1 and victim2 each send identical benign bytes and both receive EXEC:1 with command output, at the attacker's HIT counter.

Evidence: `evidence/ev_r15_E_k3b_victim_client_stream.hex`

## Artifact index

- `evidence/ev_r15_E_k3b_victim_client_stream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
