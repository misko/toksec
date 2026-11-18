# Security audit — run 61cc738c — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Transfer-Encoding is filtered out of the forwarded headers, so a chunked POST reaches the upstream bodiless and the leftover framing is a 400.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Chunked POST body is refused with 400 because TE is dropped from the forward set | line 67 (`proxy`) | `evidence/ev_r15_G_61cc_chunkpre.log` |

## Findings

### SEC-001 — Chunked POST body is refused with 400 because TE is dropped from the forward set

Transfer-Encoding is filtered out of the forwarded headers, so a chunked POST reaches the upstream bodiless and the leftover framing is a 400.

Evidence: `evidence/ev_r15_G_61cc_chunkpre.log`

## Artifact index

- `evidence/ev_r15_G_61cc_chunkpre.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
