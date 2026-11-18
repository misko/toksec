# Security audit — run 063b0d5e — release/000002 (round 9, lane K)

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
| SEC-001 | yes | low | A chunked response is abandoned mid-stream on a keep-alive connection without a terminating chunk | line 72 (`c.uraw.size()>1024`) | `evidence/ev_r9_K_trunc_063.log` |

## Findings

### SEC-001 — A chunked response is abandoned mid-stream on a keep-alive connection without a terminating chunk

Re-chunking is correct for the bytes it forwards, but when the chunk-size line is not yet buffered beyond 1024 bytes the path gives up and the client keeps a Connection: keep-alive chunked stream with no 0-terminator, so the client blocks until its own timeout. Precondition: a chunked upstream whose chunk-size line straddles the buffer.

Evidence: `evidence/ev_r9_K_trunc_063.log`, `evidence/ev_r9_K_hang_063z4.log`

## Artifact index

- `evidence/ev_r9_K_trunc_063.log`
- `evidence/ev_r9_K_hang_063z4.log`

## Limitations

- Upstream-host execution only; no local executor in the corpus.
- Needs an attacker-influenced upstream to choose the response bytes.
- The framing defects are client-side; the first hop still executes through the normal RCE.
