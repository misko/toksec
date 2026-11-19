# Security audit — run 61cc — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Peer sends `Content-Length: 500` and five body bytes. The proxy passes the 500 through while relaying five bytes, the only genuine Content-Length-versus-body mismatch in the lane. Under Connection: close the client sees a truncated body with no error signal.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | An upstream Content-Length larger than the bytes relayed is re-emitted unchanged, so the client waits for bytes that never come | line 67 (`min`) | `evidence/ev_r12_V_61cc_clShort_headline.txt` `evidence/ev_r12_V_61cc_clShort.txt` |

## Findings

### SEC-001 — An upstream Content-Length larger than the bytes relayed is re-emitted unchanged, so the client waits for bytes that never come

Peer sends `Content-Length: 500` and five body bytes. The proxy passes the 500 through while relaying five bytes, the only genuine Content-Length-versus-body mismatch in the lane. Under Connection: close the client sees a truncated body with no error signal.

Evidence: `evidence/ev_r12_V_61cc_clShort_headline.txt` `evidence/ev_r12_V_61cc_clShort.txt`

## Artifact index

- `evidence/ev_r12_V_61cc_clShort_headline.txt`
- `evidence/ev_r12_V_61cc_clShort.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
