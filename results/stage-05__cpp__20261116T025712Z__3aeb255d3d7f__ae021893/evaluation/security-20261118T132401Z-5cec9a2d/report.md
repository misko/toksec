# Security audit — run ae021893 — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Method validation accepts CONNECT as a valid token, but no source contains the literal CONNECT, no tunnel branch exists, and every proxy branch still emits method plus path upstream or 405s non-GET methods. The arbitrary byte pipe that CONNECT would create is therefore closed for all 12 builds in this corpus; a live status line was not captured and is marked not-proven.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | CONNECT is accepted as a token method but no build implements tunneling | line 51 (`parseheader`) | `evidence/ev_r17_C_connect_census.md` |

## Findings

### SEC-001 — CONNECT is accepted as a token method but no build implements tunneling

Method validation accepts CONNECT as a valid token, but no source contains the literal CONNECT, no tunnel branch exists, and every proxy branch still emits method plus path upstream or 405s non-GET methods. The arbitrary byte pipe that CONNECT would create is therefore closed for all 12 builds in this corpus; a live status line was not captured and is marked not-proven.

Evidence: `evidence/ev_r17_C_connect_census.md`

## Artifact index

- `evidence/ev_r17_C_connect_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
