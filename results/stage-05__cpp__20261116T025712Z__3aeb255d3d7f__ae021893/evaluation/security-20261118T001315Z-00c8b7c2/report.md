# Security audit — run ae021893 — release/000001 (round 11, lane Q)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same four stalls and same silent zero-byte close; 64 held slots reset the 65th client; all 38 accepted shapes agree. `43over2` (two 600000-byte chunks) is a 413 raised at `:58` on `n>limit-out.size()` before any write, so an over-large chunk is refused rather than truncated.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Same slot stall and 65th-connection reset; body cap is enforced before the write | line 74 (`maxconn`) | `evidence/ev_r11_Q_3aeb255d3d7f__ae021893_Z1.log` |

## Findings

### SEC-001 — Same slot stall and 65th-connection reset; body cap is enforced before the write

Same four stalls and same silent zero-byte close; 64 held slots reset the 65th client; all 38 accepted shapes agree. `43over2` (two 600000-byte chunks) is a 413 raised at `:58` on `n>limit-out.size()` before any write, so an over-large chunk is refused rather than truncated.

Evidence: `evidence/ev_r11_Q_3aeb255d3d7f__ae021893_Z1.log`

## Artifact index

- `evidence/ev_r11_Q_3aeb255d3d7f__ae021893_Z1.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
