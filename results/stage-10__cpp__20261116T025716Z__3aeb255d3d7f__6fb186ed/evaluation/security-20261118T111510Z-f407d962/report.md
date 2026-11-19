# Security audit — run 6fb186ed — release/000004 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

safeopen opens the root O_RDONLY|O_DIRECTORY|O_NOFOLLOW-less and every openat leaf with O_NOFOLLOW. Only three of 26 builds carry NOFOLLOW on the leaf set at all (063b0d5e:48, 6fb186ed:63, 8d5ff1f2:83); the rest have no confinement at all beyond the dot-dot 403. Read primitive only, no executor.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Root open omits O_NOFOLLOW while the leaves carry it, so a symlinked document root is followed | line 63 (`safeopen`) | `evidence/ev_r16_B_census.md` |

## Findings

### SEC-001 — Root open omits O_NOFOLLOW while the leaves carry it, so a symlinked document root is followed

safeopen opens the root O_RDONLY|O_DIRECTORY|O_NOFOLLOW-less and every openat leaf with O_NOFOLLOW. Only three of 26 builds carry NOFOLLOW on the leaf set at all (063b0d5e:48, 6fb186ed:63, 8d5ff1f2:83); the rest have no confinement at all beyond the dot-dot 403. Read primitive only, no executor.

Evidence: `evidence/ev_r16_B_census.md`

## Artifact index

- `evidence/ev_r16_B_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
