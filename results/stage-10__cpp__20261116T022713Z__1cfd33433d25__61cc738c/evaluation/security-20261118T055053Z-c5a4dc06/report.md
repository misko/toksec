# Security audit — run 61cc738c — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Bytes 0x09-0x0D at mid-path/space positions decode and reach the upstream line, splitting it into 4 tokens.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Decoded 0x09-0x0D splits upstream request line into 4 tokens | line 63 (`pathnorm`) | `evidence/ev_r13_D_peer.py` `evidence/ev_r13_D_peer2.py` `evidence/ev_r13_D_client.py` `evidence/ev_r13_D_cfg.py` `evidence/ev_r13_D_run.py` `evidence/ev_r13_D_run2.py` |

## Findings

### SEC-001 — Decoded 0x09-0x0D splits upstream request line into 4 tokens

Bytes 0x09-0x0D at mid-path/space positions decode and reach the upstream line, splitting it into 4 tokens.

Evidence: `evidence/ev_r13_D_peer.py` `evidence/ev_r13_D_peer2.py` `evidence/ev_r13_D_client.py` `evidence/ev_r13_D_cfg.py` `evidence/ev_r13_D_run.py` `evidence/ev_r13_D_run2.py`

## Artifact index

- `evidence/ev_r13_D_peer.py`
- `evidence/ev_r13_D_peer2.py`
- `evidence/ev_r13_D_client.py`
- `evidence/ev_r13_D_cfg.py`
- `evidence/ev_r13_D_run.py`
- `evidence/ev_r13_D_run2.py`

## Limitations

- All RCE in this corpus is RCE on the upstream host
