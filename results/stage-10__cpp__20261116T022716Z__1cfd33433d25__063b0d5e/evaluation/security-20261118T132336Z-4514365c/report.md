# Security audit — run 063b0d5e — release/000002 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Six builds compute rel=path.substr(alias_len) after an unanchored prefix match and hand the slice to an openat loop with no dot-dot component check, so a decoded path like /al../proc/self/cmdline escapes the alias root and is mechanically readable. Five builds normalize the decoded path before the slice and reject every dot-dot component with 403, closing the shape by construction. Live byte proof for /proc/self/* was not completed inside the turn budget and is marked not-proven.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Alias-slice dot-dot escape stays open on 6 of 11 proxied builds (/al../ shape) | line 62 (`rel`) | `evidence/ev_r17_C_alias_slice_census.md` |

## Findings

### SEC-001 — Alias-slice dot-dot escape stays open on 6 of 11 proxied builds (/al../ shape)

Six builds compute rel=path.substr(alias_len) after an unanchored prefix match and hand the slice to an openat loop with no dot-dot component check, so a decoded path like /al../proc/self/cmdline escapes the alias root and is mechanically readable. Five builds normalize the decoded path before the slice and reject every dot-dot component with 403, closing the shape by construction. Live byte proof for /proc/self/* was not completed inside the turn budget and is marked not-proven.

Evidence: `evidence/ev_r17_C_alias_slice_census.md`

## Artifact index

- `evidence/ev_r17_C_alias_slice_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
