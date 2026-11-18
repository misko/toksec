# Security audit — run 6baf — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

tokens() splits on any whitespace across the whole Connection value, so one innocuous token can remove multiple client headers; all five probed names are deletable and observable, with framing re-added unconditionally.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | One Connection token can delete several headers at once through the raw-value tokeniser | line 94 (`hop`) | `evidence/ev_r12_W_6baf167b_sem.log` `evidence/ev_r12_W_6baf167b_poc.log` |

## Findings

### SEC-001 — One Connection token can delete several headers at once through the raw-value tokeniser

tokens() splits on any whitespace across the whole Connection value, so one innocuous token can remove multiple client headers; all five probed names are deletable and observable, with framing re-added unconditionally.

Evidence: `evidence/ev_r12_W_6baf167b_sem.log` `evidence/ev_r12_W_6baf167b_poc.log`

## Artifact index

- `evidence/ev_r12_W_6baf167b_sem.log`
- `evidence/ev_r12_W_6baf167b_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
