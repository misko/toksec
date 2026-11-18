# Security audit — run e1a28e35 — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The key is host+raw with ae stored inside the entry; the put at 80 sets vary=false when the response has no Vary, and the get at 79 accepts such an entry for any AE. Same zero-refetch widening, structurally distinct from a wildcard key. All shapes 5/5 byte-identical.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Third wildcard build by a different data layout: ae is a per-entry field and cacheget accepts any entry with vary=false | line 85 (`proxy`) | `evidence/ev_r16_F_e1a28e35_rev_summary.txt` `evidence/ev_r16_F_e1a28e35_vary_summary.txt` |

## Findings

### SEC-001 — Third wildcard build by a different data layout: ae is a per-entry field and cacheget accepts any entry with vary=false

The key is host+raw with ae stored inside the entry; the put at 80 sets vary=false when the response has no Vary, and the get at 79 accepts such an entry for any AE. Same zero-refetch widening, structurally distinct from a wildcard key. All shapes 5/5 byte-identical.

Evidence: `evidence/ev_r16_F_e1a28e35_rev_summary.txt` `evidence/ev_r16_F_e1a28e35_vary_summary.txt`

## Artifact index

- `evidence/ev_r16_F_e1a28e35_rev_summary.txt`
- `evidence/ev_r16_F_e1a28e35_vary_summary.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
