# Security audit — run 6fb186ed — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Decoded control bytes reach the upstream line and split it.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Same 0x09-0x0D split on 6fb186ed | line 56 (`decodepath`) | `evidence/ev_r13_D_peer.py` `evidence/ev_r13_D_peer2.py` `evidence/ev_r13_D_client.py` `evidence/ev_r13_D_cfg.py` `evidence/ev_r13_D_run.py` `evidence/ev_r13_D_run2.py` |

## Findings

### SEC-001 — Same 0x09-0x0D split on 6fb186ed

Decoded control bytes reach the upstream line and split it.

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
