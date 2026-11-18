# Security audit — run 8d5ff1f2 — release/000002 (round 9, lane K)

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
| SEC-001 | yes | low | Response rebuild is clean on this build; the only defect is a bogus reason phrase on a 204 | line 82 (`Content-Length`) | `evidence/ev_r9_K_8d5ff1f2_fulllog.log` |

## Findings

### SEC-001 — Response rebuild is clean on this build; the only defect is a bogus reason phrase on a 204

TE is stripped, Content-Length recomputed, and an illegal chunk is 502, so the framing holds for every driven shape. The one anomaly is the cosmetic 204 Error status line from the shared reason table. Recorded as the contrast build.

Evidence: `evidence/ev_r9_K_8d5ff1f2_fulllog.log`

## Artifact index

- `evidence/ev_r9_K_8d5ff1f2_fulllog.log`

## Limitations

- Upstream-host execution only; no local executor in the corpus.
- Needs an attacker-influenced upstream to choose the response bytes.
- The framing defects are client-side; the first hop still executes through the normal RCE.
