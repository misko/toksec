# Security audit — run e1a28e35 — release/000002 (round 11, lane S)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`acquire` scans the per-authority vector and returns the top fd only on EAGAIN (`:81`), and `recycle` returns any fd with an HTTP/1.1 head and an empty buffer (`:82`). The replay pair leaks 10/10 from cold servers and 50/50 on a keep-alive connection; because it is deterministic the exec output crosses clients without the victim asking for `/exec`, 13/20. Populated-socket and truncated-body sub-probes are clean, so the leak needs the upstream to write after the peek — which it controls.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The same check-then-use makes the stale-response leak fully deterministic, so a victim receives exec output it never requested | line 81 (`acquire`) | `evidence/ev_r11_S_headline_1cfd33433d25__e1a28e35.txt` `evidence/ev_r11_S_cold_e1a.txt` `evidence/ev_r11_S_exec3_e1a.txt` |

## Findings

### SEC-001 — The same check-then-use makes the stale-response leak fully deterministic, so a victim receives exec output it never requested

`acquire` scans the per-authority vector and returns the top fd only on EAGAIN (`:81`), and `recycle` returns any fd with an HTTP/1.1 head and an empty buffer (`:82`). The replay pair leaks 10/10 from cold servers and 50/50 on a keep-alive connection; because it is deterministic the exec output crosses clients without the victim asking for `/exec`, 13/20. Populated-socket and truncated-body sub-probes are clean, so the leak needs the upstream to write after the peek — which it controls.

Evidence: `evidence/ev_r11_S_headline_1cfd33433d25__e1a28e35.txt` `evidence/ev_r11_S_cold_e1a.txt` `evidence/ev_r11_S_exec3_e1a.txt`

## Artifact index

- `evidence/ev_r11_S_headline_1cfd33433d25__e1a28e35.txt`
- `evidence/ev_r11_S_cold_e1a.txt`
- `evidence/ev_r11_S_exec3_e1a.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
