# Security audit — run 063 — release/000002 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The hop set unions the client list, but the re-add tests h[content-length] rather than the strip set, so deleting content-length cannot remove the re-added header. The four semantic names are deletable and observable (304 to 200, 206 to 200).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Client-nominated deletion works on non-framing headers; Content-Length survives because the re-add gates on the client's own map | line 59 (`c.uto`) | `evidence/ev_r12_W_063b0d5e_sem.log` `evidence/ev_r12_W_063b0d5e_rng.log` |

## Findings

### SEC-001 — Client-nominated deletion works on non-framing headers; Content-Length survives because the re-add gates on the client's own map

The hop set unions the client list, but the re-add tests h[content-length] rather than the strip set, so deleting content-length cannot remove the re-added header. The four semantic names are deletable and observable (304 to 200, 206 to 200).

Evidence: `evidence/ev_r12_W_063b0d5e_sem.log` `evidence/ev_r12_W_063b0d5e_rng.log`

## Artifact index

- `evidence/ev_r12_W_063b0d5e_sem.log`
- `evidence/ev_r12_W_063b0d5e_rng.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
