# Security audit — run f2b3415b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Same shape on the other decoder: boundary arithmetic leaves the appended request parseable, two connections and exec.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | A second request appended after the chunk terminator executes on the upstream | line 63 (`chunks`) | `evidence/ev_r15_G_f2b_chunkpost.log` |

## Findings

### SEC-001 — A second request appended after the chunk terminator executes on the upstream

Same shape on the other decoder: boundary arithmetic leaves the appended request parseable, two connections and exec.

Evidence: `evidence/ev_r15_G_f2b_chunkpost.log`

## Artifact index

- `evidence/ev_r15_G_f2b_chunkpost.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
