# Security audit — run 6baf167b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Chunk decoder leaves the post-terminator bytes in the buffer and the parse loop picks them up as a new request: two connections, exec fired.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | A second request appended after the chunk terminator executes on the upstream | line 76 (`used=x+2`) | `evidence/ev_r15_G_6baf_chunkpost.log` |

## Findings

### SEC-001 — A second request appended after the chunk terminator executes on the upstream

Chunk decoder leaves the post-terminator bytes in the buffer and the parse loop picks them up as a new request: two connections, exec fired.

Evidence: `evidence/ev_r15_G_6baf_chunkpost.log`

## Artifact index

- `evidence/ev_r15_G_6baf_chunkpost.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
