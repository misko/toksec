# Security audit — run 063b0d5e — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

All 32 bytes 0x01-0x1f and 0x7f driven; only 0x09 survives. The same loop that copies the value runs the predicate (c<32&&c!=	)||c==127 and calls upstream_fail(c,502), discarding the peer header. Control on the same config returns 200 with the header.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value collapses to 502 on any control byte except HTAB | line 69 (`upstream_fail`) | `evidence/ev_r15_F_build_1cfd33433d25__063b0d5e.txt` |

## Findings

### SEC-001 — Upstream response-header value collapses to 502 on any control byte except HTAB

All 32 bytes 0x01-0x1f and 0x7f driven; only 0x09 survives. The same loop that copies the value runs the predicate (c<32&&c!=	)||c==127 and calls upstream_fail(c,502), discarding the peer header. Control on the same config returns 200 with the header.

Evidence: `evidence/ev_r15_F_build_1cfd33433d25__063b0d5e.txt`

## Artifact index

- `evidence/ev_r15_F_build_1cfd33433d25__063b0d5e.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
