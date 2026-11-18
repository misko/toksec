# Security audit — run 6baf167b — release/000001 (round 11, lane S)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`UpConn pool` is a member of each detached worker, so the victim has to meet the armed worker: 60 sequential requests produced 60 distinct sockets, 0/9 reuse even on one kept-alive connection. The replay pair leaks 10/50 with deliberate keep-alive affinity and 0/30 one-shot, so it is a negative as a steerable leak but a real latent defect: there is no peek, so a single stray byte is re-read by the next `Reader` and fails the parse rather than being discarded. `reusable` is set from the head and `rd.b.empty()` (`:99`, `:100`), and the retry asymmetry of the sibling builds also applies.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The pool has no liveness check at all and is per-worker, so a stray upstream byte corrupts the next response parse instead of being dropped | line 96 (`upstream_once`) | `evidence/ev_r11_S_affinity_6baf.txt` `evidence/ev_r11_S_reuse_6baf_sameconn.txt` |

## Findings

### SEC-001 — The pool has no liveness check at all and is per-worker, so a stray upstream byte corrupts the next response parse instead of being dropped

`UpConn pool` is a member of each detached worker, so the victim has to meet the armed worker: 60 sequential requests produced 60 distinct sockets, 0/9 reuse even on one kept-alive connection. The replay pair leaks 10/50 with deliberate keep-alive affinity and 0/30 one-shot, so it is a negative as a steerable leak but a real latent defect: there is no peek, so a single stray byte is re-read by the next `Reader` and fails the parse rather than being discarded. `reusable` is set from the head and `rd.b.empty()` (`:99`, `:100`), and the retry asymmetry of the sibling builds also applies.

Evidence: `evidence/ev_r11_S_affinity_6baf.txt` `evidence/ev_r11_S_reuse_6baf_sameconn.txt`

## Artifact index

- `evidence/ev_r11_S_affinity_6baf.txt`
- `evidence/ev_r11_S_reuse_6baf_sameconn.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
