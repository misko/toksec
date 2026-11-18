# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

After poisoning /api/x?<smug>, victims to /api/x (no query), /api?x, /api/?x, /?x and /alpha?x all fetch upstream again (hit counts 4,5,6,6 then local 404) with EXEC:0 in every line; /?x serves the local static index and /alpha 404s. The cache key is host+full raw target, so the wildcard is only on the Accept-Encoding suffix, never on the path prefix. Same result on afdc173f, e1a28e35 and 6baf167b.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Prefix-root poisoning is closed: /, /api, /api/ and /alpha do not inherit the poisoned entry | line 70 (``) | `evidence/ev_r17_D_root_a4ba_victim_xq.hex` `evidence/ev_r17_D_root_a4ba_apiq.hex` `evidence/ev_r17_D_root_a4ba_apixq.hex` `evidence/ev_r17_D_root_a4ba_slashq.hex` |

## Findings

### SEC-001 — Prefix-root poisoning is closed: /, /api, /api/ and /alpha do not inherit the poisoned entry

After poisoning /api/x?<smug>, victims to /api/x (no query), /api?x, /api/?x, /?x and /alpha?x all fetch upstream again (hit counts 4,5,6,6 then local 404) with EXEC:0 in every line; /?x serves the local static index and /alpha 404s. The cache key is host+full raw target, so the wildcard is only on the Accept-Encoding suffix, never on the path prefix. Same result on afdc173f, e1a28e35 and 6baf167b.

Evidence: `evidence/ev_r17_D_root_a4ba_victim_xq.hex` `evidence/ev_r17_D_root_a4ba_apiq.hex` `evidence/ev_r17_D_root_a4ba_apixq.hex` `evidence/ev_r17_D_root_a4ba_slashq.hex`

## Artifact index

- `evidence/ev_r17_D_root_a4ba_victim_xq.hex`
- `evidence/ev_r17_D_root_a4ba_apiq.hex`
- `evidence/ev_r17_D_root_a4ba_apixq.hex`
- `evidence/ev_r17_D_root_a4ba_slashq.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
