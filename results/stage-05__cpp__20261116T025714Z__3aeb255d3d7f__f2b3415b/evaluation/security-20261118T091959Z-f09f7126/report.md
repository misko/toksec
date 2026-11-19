# Security audit — run f2b3415b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

1 connection, body framed by CL; no replay on the Connection: token shape.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Body is framed normally, so the preamble body does not escape the frame | line 87 (`startup`) | `evidence/ev_r15_G_f2b_conncl.log` |

## Findings

### SEC-001 — Body is framed normally, so the preamble body does not escape the frame

1 connection, body framed by CL; no replay on the Connection: token shape.

Evidence: `evidence/ev_r15_G_f2b_conncl.log`

## Artifact index

- `evidence/ev_r15_G_f2b_conncl.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
