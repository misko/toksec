# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(chunk trailing byte delivered to the client)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | transfer — 61cc738c proxy | line 67 (`proxy`) | `evidence/ev_r14_A_chunkclean_61cc_out.log` `evidence/ev_r14_A_te_61cc.log` `evidence/ev_r14_A_te_61cc_repeat.log` `evidence/ev_r14_A_te_refnginx_out.log` |

## Findings

### SEC-001 — transfer — 61cc738c proxy

(chunk trailing byte delivered to the client)

Evidence: `evidence/ev_r14_A_chunkclean_61cc_out.log` `evidence/ev_r14_A_te_61cc.log` `evidence/ev_r14_A_te_61cc_repeat.log` `evidence/ev_r14_A_te_refnginx_out.log`

## Artifact index

- `evidence/ev_r14_A_chunkclean_61cc_out.log`
- `evidence/ev_r14_A_te_61cc.log`
- `evidence/ev_r14_A_te_61cc_repeat.log`
- `evidence/ev_r14_A_te_refnginx_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
