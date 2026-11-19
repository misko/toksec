# Security audit — run ae021893 — release/000001 (round 11, lane D)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

All 32 byte classes pass with the 3-token upstream line intact.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | ae021893 full-pass build on the byte sweep | line 51 (`parseheader`) | `evidence/ev_r13_D_peer.py` `evidence/ev_r13_D_peer2.py` `evidence/ev_r13_D_client.py` `evidence/ev_r13_D_cfg.py` `evidence/ev_r13_D_run.py` `evidence/ev_r13_D_run2.py` |

## Findings

### SEC-001 — ae021893 full-pass build on the byte sweep

All 32 byte classes pass with the 3-token upstream line intact.

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
