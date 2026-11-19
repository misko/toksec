# Security audit — run 6baf167b — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The built-in exact-key build (cachekey = host+target+'\n'+AE, line 88) behaves identically on these depth probes: /api?x, /api/?x and /?x refetch, /?x serves the local static index. Its only cache-key divergence from the other three is the missing wildcard arm on Accept-Encoding, confirmed separately below.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Negative contrast: 6baf167b exact key including Accept-Encoding also never widens to a prefix | line 88 (``) | `evidence/ev_r17_D_root_6baf_apiq.hex` `evidence/ev_r17_D_root_6baf_apixq.hex` `evidence/ev_r17_D_root_6baf_slashq.hex` |

## Findings

### SEC-001 — Negative contrast: 6baf167b exact key including Accept-Encoding also never widens to a prefix

The built-in exact-key build (cachekey = host+target+'\n'+AE, line 88) behaves identically on these depth probes: /api?x, /api/?x and /?x refetch, /?x serves the local static index. Its only cache-key divergence from the other three is the missing wildcard arm on Accept-Encoding, confirmed separately below.

Evidence: `evidence/ev_r17_D_root_6baf_apiq.hex` `evidence/ev_r17_D_root_6baf_apixq.hex` `evidence/ev_r17_D_root_6baf_slashq.hex`

## Artifact index

- `evidence/ev_r17_D_root_6baf_apiq.hex`
- `evidence/ev_r17_D_root_6baf_apixq.hex`
- `evidence/ev_r17_D_root_6baf_slashq.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
