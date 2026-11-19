# Security audit — run 29d — release/000002 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The forward loop unions a fixed hop list with the client's Connection tokens, then re-emits only surviving headers with no Content-Length re-add and no body streaming. range, if-none-match, accept-encoding and authorization are all deleted on the client's word, changing the upstream's answer (304 becomes 200, 206 becomes 200). POST is refused at the method gate, so the unframed-body shape cannot fire.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The client-nominated deletion set removes every probed non-framing header from the forwarded request | line 50 (`c.upout`) | `evidence/ev_r12_W_29d05850_sem.log` `evidence/ev_r12_W_29d05850_poc.log` |

## Findings

### SEC-001 — The client-nominated deletion set removes every probed non-framing header from the forwarded request

The forward loop unions a fixed hop list with the client's Connection tokens, then re-emits only surviving headers with no Content-Length re-add and no body streaming. range, if-none-match, accept-encoding and authorization are all deleted on the client's word, changing the upstream's answer (304 becomes 200, 206 becomes 200). POST is refused at the method gate, so the unframed-body shape cannot fire.

Evidence: `evidence/ev_r12_W_29d05850_sem.log` `evidence/ev_r12_W_29d05850_poc.log`

## Artifact index

- `evidence/ev_r12_W_29d05850_sem.log`
- `evidence/ev_r12_W_29d05850_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
