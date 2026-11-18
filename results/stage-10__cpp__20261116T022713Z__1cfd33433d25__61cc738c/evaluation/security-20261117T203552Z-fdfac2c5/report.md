# Security audit — run 61cc738c — release/000001 (round 9, lane K)

The response the proxy rebuilds for the client. Release source read from the tag and
byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; the proxy execs nothing. This lane is client-side framing.

## Audit narrative

Control first on the same config: a plain 200 with Content-Length 5 delivered HELLO on every
build. A scripted peer then emitted, one path each, an interim, a chunked body, chunked trailers,
a junk and an overlong reason phrase, an upstream Connection: close on a keep-alive client, a 204
with CL, and a static-and-proxy collision path. Client heads were captured verbatim and the
follow-up request on the same connection was used to test the frame.



## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A chunked upstream response is forwarded with both Transfer-Encoding: chunked and a recomputed Content-Length, and the raw chunk bytes are then truncated to that length | line 67 (`chunked`) | `evidence/ev_r9_K_61cc738c_fulllog.log` |

## Findings

### SEC-001 — A chunked upstream response is forwarded with both Transfer-Encoding: chunked and a recomputed Content-Length, and the raw chunk bytes are then truncated to that length

The head builder appends Transfer-Encoding: chunked when the upstream was chunked and separately appends Content-Length from its parse, so the client head carries both. The body then consists of the upstream's raw chunk bytes cut at the Content-Length, so neither a TE client nor a CL client gets a well-framed body, and every chunked response is truncated. Precondition: any chunked upstream response.

Evidence: `evidence/ev_r9_K_61cc738c_fulllog.log`

## Artifact index

- `evidence/ev_r9_K_61cc738c_fulllog.log`

## Limitations

- Upstream-host execution only; no local executor in the corpus.
- Needs an attacker-influenced upstream to choose the response bytes.
- The framing defects are client-side; the first hop still executes through the normal RCE.
