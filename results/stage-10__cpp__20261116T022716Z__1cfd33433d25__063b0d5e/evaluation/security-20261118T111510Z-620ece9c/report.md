# Security audit — run 063b0d5e — release/000002 (round 11, lane B)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Census negative: every build returns 403 on any .. segment instead of resolving it. Combined with an open-all O_NOFOLLOW leaf walk, a legitimate nested path holding a .. is unreachable. Two levels of .. also 403 on 6baf. Read-only consequence.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Dot-dot is refused 403 rather than resolved, so confinement is by rejection and traversal never normalises | line 48 (`openconfined`) | `evidence/ev_r16_B_census.md` |

## Findings

### SEC-001 — Dot-dot is refused 403 rather than resolved, so confinement is by rejection and traversal never normalises

Census negative: every build returns 403 on any .. segment instead of resolving it. Combined with an open-all O_NOFOLLOW leaf walk, a legitimate nested path holding a .. is unreachable. Two levels of .. also 403 on 6baf. Read-only consequence.

Evidence: `evidence/ev_r16_B_census.md`

## Artifact index

- `evidence/ev_r16_B_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
