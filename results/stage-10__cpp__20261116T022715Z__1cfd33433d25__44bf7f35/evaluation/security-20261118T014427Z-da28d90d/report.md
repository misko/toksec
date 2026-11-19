# Security audit — run 44bf — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Two Content-Length headers are both accepted and both would be emitted; the proxy then resizes the body to the last value. A first-wins client and a last-wins client therefore disagree with the proxy about framing.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Duplicate Content-Length headers are not de-duplicated; the last value wins and the body is cut to it | line 87 (`body.resize`) | `evidence/ev_r12_V_44bf_dupCL_firstwins.txt` `evidence/ev_r12_V_44bf_dupCLlast.txt` `evidence/ev_r12_V_44bf_dupCL.txt` |

## Findings

### SEC-001 — Duplicate Content-Length headers are not de-duplicated; the last value wins and the body is cut to it

Two Content-Length headers are both accepted and both would be emitted; the proxy then resizes the body to the last value. A first-wins client and a last-wins client therefore disagree with the proxy about framing.

Evidence: `evidence/ev_r12_V_44bf_dupCL_firstwins.txt` `evidence/ev_r12_V_44bf_dupCLlast.txt` `evidence/ev_r12_V_44bf_dupCL.txt`

## Artifact index

- `evidence/ev_r12_V_44bf_dupCL_firstwins.txt`
- `evidence/ev_r12_V_44bf_dupCLlast.txt`
- `evidence/ev_r12_V_44bf_dupCL.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
