# Security audit — run afdc173f — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

cacheget iterates {base+
*, base+
+enc}; the store at 78 writes * when there is no Vary. Widening holds for every differing AE. Because wildcard is probed before exact, an installed wildcard makes a valid exact entry unreachable, which a4ba853a does not do (exact first). That ordering difference is a driveable row, not a hypothesis.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Second, independent wildcard store, and it probes the wildcard FIRST so an installed wildcard shadows a correct exact entry | line 77 (`cacheget`) | `evidence/ev_r16_F_afdc173f_rev_summary.txt` `evidence/ev_r16_F_afdc173f_order_summary.txt` |

## Findings

### SEC-001 — Second, independent wildcard store, and it probes the wildcard FIRST so an installed wildcard shadows a correct exact entry

cacheget iterates {base+
*, base+
+enc}; the store at 78 writes * when there is no Vary. Widening holds for every differing AE. Because wildcard is probed before exact, an installed wildcard makes a valid exact entry unreachable, which a4ba853a does not do (exact first). That ordering difference is a driveable row, not a hypothesis.

Evidence: `evidence/ev_r16_F_afdc173f_rev_summary.txt` `evidence/ev_r16_F_afdc173f_order_summary.txt`

## Artifact index

- `evidence/ev_r16_F_afdc173f_rev_summary.txt`
- `evidence/ev_r16_F_afdc173f_order_summary.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
