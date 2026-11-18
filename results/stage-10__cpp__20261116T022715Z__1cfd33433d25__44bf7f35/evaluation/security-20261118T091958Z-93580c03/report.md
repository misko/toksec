# Security audit — run 44bf7f35 — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

proxy_simple sends only the synthesised header block, so the de-chunked body never goes upstream. The leftover chunk framing is handed back to the proxy own parser and answered 400 after the real 200.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A chunked POST body is dropped entirely and a spurious trailing 400 is emitted | line 87 (`proxy_simple`) | `evidence/ev_r15_G_44bf_chunkpre.log` |

## Findings

### SEC-001 — A chunked POST body is dropped entirely and a spurious trailing 400 is emitted

proxy_simple sends only the synthesised header block, so the de-chunked body never goes upstream. The leftover chunk framing is handed back to the proxy own parser and answered 400 after the real 200.

Evidence: `evidence/ev_r15_G_44bf_chunkpre.log`

## Artifact index

- `evidence/ev_r15_G_44bf_chunkpre.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
