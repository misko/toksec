# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Control first: two identical /api/zz.txt requests hit the cache (two fetches total, second serves the stored body). A single identity-AE request to /api/x?smuggled<CR><LF>GET /exec?cmd=id then poisons the exact key host+/api/x?<smug>. The first victim to the identical target refetches it (upstream line captured with the smuggled second request inside), and every later identical victim is served from cache at zero fetches (see ev_r17_D_xae rows for the explicit zero-fetch confirmation), so one attack request claims one exact key and the exec output it produces.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Poison key is the exact raw target; identity-AE attack repels only the byte-identical victim request | line 70 (``) | `evidence/ev_r17_D_ctl_a4ba_attack.hex` `evidence/ev_r17_D_root_a4ba_victim_xq.hex` `evidence/ev_r17_D_root_a4ba_up_victim.hex` `evidence/ev_r17_D_ctl_a4ba_up_attack.hex` |

## Findings

### SEC-001 — Poison key is the exact raw target; identity-AE attack repels only the byte-identical victim request

Control first: two identical /api/zz.txt requests hit the cache (two fetches total, second serves the stored body). A single identity-AE request to /api/x?smuggled<CR><LF>GET /exec?cmd=id then poisons the exact key host+/api/x?<smug>. The first victim to the identical target refetches it (upstream line captured with the smuggled second request inside), and every later identical victim is served from cache at zero fetches (see ev_r17_D_xae rows for the explicit zero-fetch confirmation), so one attack request claims one exact key and the exec output it produces.

Evidence: `evidence/ev_r17_D_ctl_a4ba_attack.hex` `evidence/ev_r17_D_root_a4ba_victim_xq.hex` `evidence/ev_r17_D_root_a4ba_up_victim.hex` `evidence/ev_r17_D_ctl_a4ba_up_attack.hex`

## Artifact index

- `evidence/ev_r17_D_ctl_a4ba_attack.hex`
- `evidence/ev_r17_D_root_a4ba_victim_xq.hex`
- `evidence/ev_r17_D_root_a4ba_up_victim.hex`
- `evidence/ev_r17_D_ctl_a4ba_up_attack.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
