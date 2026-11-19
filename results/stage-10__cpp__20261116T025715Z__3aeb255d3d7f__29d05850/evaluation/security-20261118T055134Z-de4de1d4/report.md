# Security audit — run 29d05850 — release/000002 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Connection: authorization strips Authorization; Connection: expect strips Expect before forwarding, allowing the split-line RCE on a strict upstream.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Same precondition-removal on 29d05850 | line 45 (`c.upout`) | `evidence/ev_r13_A_peer.py` `evidence/ev_r13_A_drive.py` `evidence/ev_r13_A_peer.log` `evidence/ev_r13_A_61cc738c_plain.log` `evidence/ev_r13_A_61cc738c_auth_plain.log` `evidence/ev_r13_A_61cc738c_auth_split.log` `evidence/ev_r13_A_61cc738c_auth_forbid.log` `evidence/ev_r13_A_61cc738c_expect.log` |

## Findings

### SEC-001 — Same precondition-removal on 29d05850

Connection: authorization strips Authorization; Connection: expect strips Expect before forwarding, allowing the split-line RCE on a strict upstream.

Evidence: `evidence/ev_r13_A_peer.py` `evidence/ev_r13_A_drive.py` `evidence/ev_r13_A_peer.log` `evidence/ev_r13_A_61cc738c_plain.log` `evidence/ev_r13_A_61cc738c_auth_plain.log` `evidence/ev_r13_A_61cc738c_auth_split.log` `evidence/ev_r13_A_61cc738c_auth_forbid.log` `evidence/ev_r13_A_61cc738c_expect.log`

## Artifact index

- `evidence/ev_r13_A_peer.py`
- `evidence/ev_r13_A_drive.py`
- `evidence/ev_r13_A_peer.log`
- `evidence/ev_r13_A_61cc738c_plain.log`
- `evidence/ev_r13_A_61cc738c_auth_plain.log`
- `evidence/ev_r13_A_61cc738c_auth_split.log`
- `evidence/ev_r13_A_61cc738c_auth_forbid.log`
- `evidence/ev_r13_A_61cc738c_expect.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
