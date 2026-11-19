# Security audit — run 8d5 — release/000002 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

proxy_request filters only the built-in names, so none of the five probed deletions took effect (control 304 and payload 304 identical). The deletion-set trust boundary is closed on this build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The strip list is fixed; the client's Connection tokens are ignored entirely | line 85 (`h.first!=`) | `evidence/ev_r12_W_8d5ff1f2_sem.log` `evidence/ev_r12_W_8d5ff1f2_rng.log` |

## Findings

### SEC-001 — The strip list is fixed; the client's Connection tokens are ignored entirely

proxy_request filters only the built-in names, so none of the five probed deletions took effect (control 304 and payload 304 identical). The deletion-set trust boundary is closed on this build.

Evidence: `evidence/ev_r12_W_8d5ff1f2_sem.log` `evidence/ev_r12_W_8d5ff1f2_rng.log`

## Artifact index

- `evidence/ev_r12_W_8d5ff1f2_sem.log`
- `evidence/ev_r12_W_8d5ff1f2_rng.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
