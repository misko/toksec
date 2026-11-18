# Security audit delta — stage-10 run 6fb186ed — release/000004 (round 6/7)

Second pass over the audited release `release/000004` (75 lines). The first envelope closed
20 findings. This pass adds the config-shape axis: the separator and the exec route can come
from the `proxy_pass` literal instead of the client request, which removes percent-encoding
from the exploit entirely.

All RCE here is **RCE on the upstream host**; the proxy has no `system`/`popen`. Findings were
re-driven on the compiled release tag with a strict peer that prints the upstream line
verbatim with a token count and fires `sh` only on an exact 3-token exec target. Every claim
has a `GET /hello.txt` static control that returns the marker body.

## Audit narrative

The first pass established request-line splitting via a decoded separator and the CL-0 body
gate. This pass asked what the proxy emits when the config supplies the separator or the
route: `uri = spec.substr(slash) + path.substr(loc->path.size()) + q` (`line 68 (substr)`).

Two forms follow with zero client encoding. A quoted trailing space in the URI makes a bare
`GET /api` emit `GET /exec  HTTP/1.1` — four tokens — which a whitespace-splitting upstream
executes with its default command. And a URI naming the route without the space keeps three
tokens, so `GET /api?cmd=whoami` emits `GET /exec?cmd=whoami HTTP/1.1` and a strict parser
runs the attacker's command.

The CL-0 gate (any non-"0" Content-Length is 400) means a POST body cannot be sent, but a
trailing request line with no CL is re-parsed and proxied on a keep-alive connection, so the
build still issues two upstream requests from one write.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Exact-match URI without a trailing space keeps a 3-token line, so an attacker query alone executes a chosen command on a strict parser | line 68 (`substr`) | `evidence/e6_exact.log` |
| SEC-002 | yes | high | A quoted space in the `proxy_pass` URI is the separator, so a bare `GET /api` executes the upstream default command with no encoding | line 68 (`substr`) | `evidence/e6_qs.log` |
| SEC-003 | yes | high | A trailing request line with no `Content-Length` survives an accepted-then-400 request and is proxied as a second request | line 67 (`content-length`) | `evidence/e6_body.log` |

## Findings

### SEC-001 — attacker-chosen command in three tokens

Precondition: `proxy_pass` URI naming the exec route with no trailing space; location path the
request matches exactly.

`GET /api?cmd=whoami` → upstream `GET /exec?cmd=whoami HTTP/1.1`, three tokens, exec
`whoami`, body `mouse9911`. Bare `GET /api` → `GET /exec HTTP/1.1`, exec `id`. The attacker
contributes only a query string and there is no decoder in the path.

### SEC-002 — quoted-space config, no query needed

Precondition: a quoted trailing space in the URI; whitespace-splitting upstream.

`GET /api` → `GET /exec  HTTP/1.1`, four tokens, exec `id`. The command is the upstream's
default, so this form executes but does not choose the command; SEC-001 does.

### SEC-003 — second request from a rejected POST

`line 67 (content-length)` rejects any CL other than the literal `0` with 400 but does not
close the connection. A POST carrying a body therefore fails, while a GET with a trailing
request line and no CL is answered 400 *and* the tail is parsed and proxied, giving a second
execution from one write. Control: `GET /hello.txt` 200.

## Artifact index

- `evidence/e6_exact.log` — control, both 3-token exec lines
- `evidence/e6_qs.log` — control, quoted-space 4-token line
- `evidence/e6_body.log` — control, 400-then-proxy body replay

## Limitations

- One build; the same shape exists on its siblings, which carry their own envelopes.
- SEC-002 needs a whitespace-splitting upstream; SEC-001 needs a strict 3-token reader.
- SEC-003 needs keep-alive.
- No memory-safety work in this pass; RCE is upstream-side only.
