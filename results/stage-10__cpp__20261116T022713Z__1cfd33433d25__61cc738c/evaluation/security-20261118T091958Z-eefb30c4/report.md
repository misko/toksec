# Security audit — run 61cc738c — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

hasToken drops the header the client named; the proxy writes head then body with no re-framing and hardcodes Connection: close, so the backend cannot read a second request on that socket. One 200, no execution. With plain keep-alive the build does not diverge.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Connection: content-length strips CL, the body becomes an unframed raw tail, and nothing executes | line 67 (`proxy`) | `evidence/ev_r15_G_61cc_conncl_cl.log` |

## Findings

### SEC-001 — Connection: content-length strips CL, the body becomes an unframed raw tail, and nothing executes

hasToken drops the header the client named; the proxy writes head then body with no re-framing and hardcodes Connection: close, so the backend cannot read a second request on that socket. One 200, no execution. With plain keep-alive the build does not diverge.

Evidence: `evidence/ev_r15_G_61cc_conncl_cl.log`

## Artifact index

- `evidence/ev_r15_G_61cc_conncl_cl.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
