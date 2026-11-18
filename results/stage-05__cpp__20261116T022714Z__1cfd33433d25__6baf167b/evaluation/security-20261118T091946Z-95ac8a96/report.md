# Security audit — run 6baf167b — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

parsefields applies the same predicate; 31 of 32 cells are 502 and only HTAB survives.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value collapses to 502 on any control byte except HTAB | line 59 (`parsefields`) | `evidence/ev_r15_F_build_1cfd33433d25__6baf167b.txt` |

## Findings

### SEC-001 — Upstream response-header value collapses to 502 on any control byte except HTAB

parsefields applies the same predicate; 31 of 32 cells are 502 and only HTAB survives.

Evidence: `evidence/ev_r15_F_build_1cfd33433d25__6baf167b.txt`

## Artifact index

- `evidence/ev_r15_F_build_1cfd33433d25__6baf167b.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
