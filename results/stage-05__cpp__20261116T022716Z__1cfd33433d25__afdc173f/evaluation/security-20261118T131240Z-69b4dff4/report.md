# Security audit — run afdc173f — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

afdc173f checks the wildcard arm first and stores the response under base|*, but the base is still the full raw target: /api?x, /api/?x and /?x all miss and refetch, /?x hits the local static handler. This is the depth contrast for the build whose store arm is always the wildcard: the wildcard saves the attacker only one AE dimension, not path breadth.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | afdc173f confirms the same key width: exact raw target, wildcard only on the encoding arm | line 75 (``) | `evidence/ev_r17_D_root_afdc_apiq.hex` `evidence/ev_r17_D_root_afdc_apixq.hex` `evidence/ev_r17_D_root_afdc_slashq.hex` |

## Findings

### SEC-001 — afdc173f confirms the same key width: exact raw target, wildcard only on the encoding arm

afdc173f checks the wildcard arm first and stores the response under base|*, but the base is still the full raw target: /api?x, /api/?x and /?x all miss and refetch, /?x hits the local static handler. This is the depth contrast for the build whose store arm is always the wildcard: the wildcard saves the attacker only one AE dimension, not path breadth.

Evidence: `evidence/ev_r17_D_root_afdc_apiq.hex` `evidence/ev_r17_D_root_afdc_apixq.hex` `evidence/ev_r17_D_root_afdc_slashq.hex`

## Artifact index

- `evidence/ev_r17_D_root_afdc_apiq.hex`
- `evidence/ev_r17_D_root_afdc_apixq.hex`
- `evidence/ev_r17_D_root_afdc_slashq.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
