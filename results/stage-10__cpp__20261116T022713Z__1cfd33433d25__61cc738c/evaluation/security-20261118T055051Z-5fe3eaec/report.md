# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Connection: authorization strips the Authorization header from the forwarded request; Connection: expect strips Expect. The decoded split-line RCE executes on a strict upstream once these preconditions are removed client-side.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Client-deletable Authorization and Expect remove upstream preconditions for the split-line RCE | line 58 (`hasToken`) | `evidence/ev_r13_A_peer.py` `evidence/ev_r13_A_drive.py` `evidence/ev_r13_A_peer.log` `evidence/ev_r13_A_61cc738c_plain.log` `evidence/ev_r13_A_61cc738c_auth_plain.log` `evidence/ev_r13_A_61cc738c_auth_split.log` `evidence/ev_r13_A_61cc738c_auth_forbid.log` `evidence/ev_r13_A_61cc738c_expect.log` |

## Findings

### SEC-001 — Client-deletable Authorization and Expect remove upstream preconditions for the split-line RCE

Connection: authorization strips the Authorization header from the forwarded request; Connection: expect strips Expect. The decoded split-line RCE executes on a strict upstream once these preconditions are removed client-side.

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
