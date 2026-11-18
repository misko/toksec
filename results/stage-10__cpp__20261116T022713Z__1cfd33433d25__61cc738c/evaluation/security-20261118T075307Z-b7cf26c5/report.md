# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(Content-Length stripped, body sent unframed) Class: framing desync; the body follows the headers as a raw tail on the same socket.
Control first: `ctl` -> 200 BODY, one upstream request (`ev_r14_A_61cc738c_v2_out.log`).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | desync — 61cc738c proxy | line 67 (`proxy`) | `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_probe_61cc.log` `evidence/ev_r14_A_probe_61cc_out.log` |

## Findings

### SEC-001 — desync — 61cc738c proxy

(Content-Length stripped, body sent unframed) Class: framing desync; the body follows the headers as a raw tail on the same socket.
Control first: `ctl` -> 200 BODY, one upstream request (`ev_r14_A_61cc738c_v2_out.log`).

Evidence: `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_probe_61cc.log` `evidence/ev_r14_A_probe_61cc_out.log`

## Artifact index

- `evidence/ev_r14_A_61cc738c_v2.log`
- `evidence/ev_r14_A_61cc738c_v2_out.log`
- `evidence/ev_r14_A_probe_61cc.log`
- `evidence/ev_r14_A_probe_61cc_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
