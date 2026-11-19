# Security audit — run 6baf167b — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The proxy re-adds Content-Length from the measured body, so the preamble body arrives as one framed body: 1 connection, no replay.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Unframed body is re-framed by the proxy as Content-Length, so there is no divergence on this build | line 97 (`Content-Length`) | `evidence/ev_r15_G_6baf_conncl.log` |

## Findings

### SEC-001 — Unframed body is re-framed by the proxy as Content-Length, so there is no divergence on this build

The proxy re-adds Content-Length from the measured body, so the preamble body arrives as one framed body: 1 connection, no replay.

Evidence: `evidence/ev_r15_G_6baf_conncl.log`

## Artifact index

- `evidence/ev_r15_G_6baf_conncl.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
