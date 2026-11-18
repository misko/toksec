# Security audit — run 6fb — release/000004 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The fixed filter plus the :67 gate leave no framed POST path, so the unframed-body RCE shape cannot fire even though the strip exists.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Fixed strip list; client tokens ignored; POST bodies are restricted to Content-Length: 0 | line 68 (`c.upsend`) | `evidence/ev_r12_W_6fb186ed_sem.log` `evidence/ev_r12_W_6fb186ed_poc.log` |

## Findings

### SEC-001 — Fixed strip list; client tokens ignored; POST bodies are restricted to Content-Length: 0

The fixed filter plus the :67 gate leave no framed POST path, so the unframed-body RCE shape cannot fire even though the strip exists.

Evidence: `evidence/ev_r12_W_6fb186ed_sem.log` `evidence/ev_r12_W_6fb186ed_poc.log`

## Artifact index

- `evidence/ev_r12_W_6fb186ed_sem.log`
- `evidence/ev_r12_W_6fb186ed_poc.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
