# Security audit delta — stage-10 run 063b0d5e — release/000002 (round 6/7)

Second pass on the audited release `release/000002` (82 lines). The first envelope closed the
decoder and `Content-Length` findings. This pass adds the config-shape axis, where the
separator and the exec route come from `proxy_pass` rather than the request.

All RCE is **RCE on the upstream host**. Driven on the compiled release with a strict peer
that prints the upstream line verbatim plus a token count and fires `sh` only on an exact
3-token exec target. `GET /hello.txt` static control before each payload.

## Audit narrative

The upstream target is `loc->uri + path.substr(min(path.size(), loc->path.size())) + query`
(`line 58 (min)`). The `min()` clamps the slice to the path length, so an exact location match
leaves the URI alone and the query attaches straight to it.

With a URI naming the exec route and no trailing space, `GET /api?cmd=whoami` emits
`GET /exec?cmd=whoami HTTP/1.1` — three tokens — and a strict parser runs `whoami`. A quoted
trailing space instead makes a bare `GET /api` emit `GET /exec  HTTP/1.1` (four tokens) and a
whitespace-splitting upstream runs the default command. Neither form uses a percent escape.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The `min()`-clamped slice leaves the URI intact on an exact match, so an attacker query alone executes a chosen command in a 3-token line | line 58 (`min`) | `evidence/e63_exact.log` |
| SEC-002 | yes | high | A quoted space in the `proxy_pass` URI is the separator, so a bare `GET /api` executes the upstream default command with no encoding | line 58 (`upath`) | `evidence/e63_qs.log` |

## Findings

### SEC-001 — chosen command, three tokens

`GET /api?cmd=whoami` → `GET /exec?cmd=whoami HTTP/1.1`, exec `whoami`, body `mouse9911`;
bare `GET /api` → `GET /exec HTTP/1.1`, exec `id`. The `min()` is what keeps the line at three
tokens for a matching request: the remainder cannot under- or over-run the path. Precondition:
a URI naming the route without a trailing space, plus a strict 3-token reader.

### SEC-002 — quoted space, no query at all

`GET /api` → `GET /exec  HTTP/1.1`, four tokens, default command executed. Precondition: the
quoted trailing space and a whitespace-splitting upstream.

## Artifact index

- `evidence/e63_exact.log` — control and both 3-token exec lines
- `evidence/e63_qs.log` — control and the 4-token quoted-space line

## Limitations

- One build; siblings carry their own envelopes.
- Precondition differs per finding (strict vs whitespace-splitting upstream), stated above.
- Upstream-side RCE only; no memory-safety work.
