# Security audit — run 063b0d5e — release/000002 (round 11, lane Q0)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`:55` fails 400 whenever the request carries `transfer-encoding`, and `:58` fails the same for a bare `Content-Length`, so no request body is ever consumed and no upstream body byte is ever emitted; chunk state on this build is response-side only. Three shapes tried, all 400 with zero upstream requests. This is the clean per-build contrast that makes the other five decoders' behaviour attributable to the decoder rather than to the proxy as a class.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Every request `Transfer-Encoding` is a 400, so this build never decodes a chunked request body at all | line 55 (`transfer-encoding`) | `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log` |

## Findings

### SEC-001 — Every request `Transfer-Encoding` is a 400, so this build never decodes a chunked request body at all

`:55` fails 400 whenever the request carries `transfer-encoding`, and `:58` fails the same for a bare `Content-Length`, so no request body is ever consumed and no upstream body byte is ever emitted; chunk state on this build is response-side only. Three shapes tried, all 400 with zero upstream requests. This is the clean per-build contrast that makes the other five decoders' behaviour attributable to the decoder rather than to the proxy as a class.

Evidence: `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log`

## Artifact index

- `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
