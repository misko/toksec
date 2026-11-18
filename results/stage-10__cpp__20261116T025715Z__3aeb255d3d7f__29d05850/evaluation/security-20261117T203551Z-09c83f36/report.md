# Security audit — run 29d05850 — release/000002 (round 9, lane K)

The response the proxy rebuilds for the client. Release source read from the tag and
byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; the proxy execs nothing. This lane is client-side framing.

## Audit narrative

Control first on the same config: a plain 200 with Content-Length 5 delivered HELLO on every
build. A scripted peer then emitted, one path each, an interim, a chunked body, chunked trailers,
a junk and an overlong reason phrase, an upstream Connection: close on a keep-alive client, a 204
with CL, and a static-and-proxy collision path. Client heads were captured verbatim and the
follow-up request on the same connection was used to test the frame.

The decisive shape is the reason phrase: it is forwarded unvalidated and a bare CR in it splits the head the proxy itself wrote.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The upstream reason phrase is copied verbatim into the client head, so a bare CR in it pre-empts headers the proxy writes | line 57 (`getline(st,reason)`) | `evidence/ev_r9_K_judge_29d1.log` |
| SEC-002 | yes | low | Content-Length is emitted on a 204, a bodyless status, when the upstream sent one | line 57 (`if(code!=204&&length>=0)`) | `evidence/ev_r9_K_61cc738c_fulllog.log` |

## Findings

### SEC-001 — The upstream reason phrase is copied verbatim into the client head, so a bare CR in it pre-empts headers the proxy writes

The status line is read with getline(st,reason) and re-emitted as HTTP/1.1 <code><reason>. A reason containing a bare CR and then header text lands those bytes before the proxy's own header block. An upstream reason of OK\rContent-Length: 999 yields a client head with a rogue Content-Length: 999 ahead of the real Content-Length: 5; with OK\rSet-Cookie: a=b two live cookies are installed. CRLF-strict clients take the first CL and starve, CR-splitting clients see three headers. Precondition: an attacker-influenced upstream.

Evidence: `evidence/ev_r9_K_judge_29d1.log`, `evidence/ev_r9_K_29d05850_fulllog.log`

### SEC-002 — Content-Length is emitted on a 204, a bodyless status, when the upstream sent one

The bodyless branch still appends Content-Length if the upstream supplied a length and the code is not 204. A 304 with Content-Length: 5 was forwarded with that CL even though no body follows, so a client that honours CL on a bodyless status waits. Precondition: an upstream that sends CL on a bodyless status.

Evidence: `evidence/ev_r9_K_61cc738c_fulllog.log`, `evidence/ev_r9_K_head_29.log`

## Artifact index

- `evidence/ev_r9_K_judge_29d1.log`
- `evidence/ev_r9_K_29d05850_fulllog.log`
- `evidence/ev_r9_K_61cc738c_fulllog.log`
- `evidence/ev_r9_K_head_29.log`

## Limitations

- Upstream-host execution only; no local executor in the corpus.
- Needs an attacker-influenced upstream to choose the response bytes.
- The framing defects are client-side; the first hop still executes through the normal RCE.
