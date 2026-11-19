# Security audit — run 44bf — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The relay loop reads the folded line as a field of its own, so `X-A: one` followed by a space-continued ` two` loses the tail and the second half is not emitted at all. When the folded field is the Content-Length the proxy falls back to the body size, so the emitted length and the upstream's intent diverge.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | An obs-folded upstream header truncates the value and silently drops the field after the fold | line 87 (`proxy_simple`) | `evidence/ev_r12_V_44bf_fold.txt` `evidence/ev_r12_V_44bf_foldCL.txt` `evidence/ev_r12_V_44bf_foldHdr.txt` |

## Findings

### SEC-001 — An obs-folded upstream header truncates the value and silently drops the field after the fold

The relay loop reads the folded line as a field of its own, so `X-A: one` followed by a space-continued ` two` loses the tail and the second half is not emitted at all. When the folded field is the Content-Length the proxy falls back to the body size, so the emitted length and the upstream's intent diverge.

Evidence: `evidence/ev_r12_V_44bf_fold.txt` `evidence/ev_r12_V_44bf_foldCL.txt` `evidence/ev_r12_V_44bf_foldHdr.txt`

## Artifact index

- `evidence/ev_r12_V_44bf_fold.txt`
- `evidence/ev_r12_V_44bf_foldCL.txt`
- `evidence/ev_r12_V_44bf_foldHdr.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
