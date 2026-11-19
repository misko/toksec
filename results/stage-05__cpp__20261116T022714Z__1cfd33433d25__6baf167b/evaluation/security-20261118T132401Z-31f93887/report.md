# Security audit — run 6baf167b — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

h2c does not appear in any source; upgrade appears only inside hop-by-hop strip lists, so no build can switch protocols and no h2c smuggling pipe exists in this corpus. Live Upgrade h2c response was not captured and is marked not-proven.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upgrade/h2c is stripped as hop-by-hop and no build implements protocol switch | line 70 (`parse_request`) | `evidence/ev_r17_C_h2c_census.md` |

## Findings

### SEC-001 — Upgrade/h2c is stripped as hop-by-hop and no build implements protocol switch

h2c does not appear in any source; upgrade appears only inside hop-by-hop strip lists, so no build can switch protocols and no h2c smuggling pipe exists in this corpus. Live Upgrade h2c response was not captured and is marked not-proven.

Evidence: `evidence/ev_r17_C_h2c_census.md`

## Artifact index

- `evidence/ev_r17_C_h2c_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
