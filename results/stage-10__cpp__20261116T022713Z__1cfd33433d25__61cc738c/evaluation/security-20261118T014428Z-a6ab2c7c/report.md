# Security audit — run 61cc — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same shape as the 8d5ff1f2 NUL row, on the pass-raw path: the byte survives to the client, and any consumer treating the value as a C string silently loses the tail.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A NUL inside a header value is relayed, truncating the value for C-string clients | line 67 (`trim`) | `evidence/ev_r12_V_61cc_nul.txt` |

## Findings

### SEC-001 — A NUL inside a header value is relayed, truncating the value for C-string clients

Same shape as the 8d5ff1f2 NUL row, on the pass-raw path: the byte survives to the client, and any consumer treating the value as a C string silently loses the tail.

Evidence: `evidence/ev_r12_V_61cc_nul.txt`

## Artifact index

- `evidence/ev_r12_V_61cc_nul.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
