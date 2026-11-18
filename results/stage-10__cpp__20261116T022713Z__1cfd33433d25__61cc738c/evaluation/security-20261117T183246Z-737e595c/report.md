# Security audit delta — stage-10 run 61cc738c — release/000001 (round 6/7)

Second pass on the audited release `release/000001` (71 lines). The first envelope covered the
`Connection: content-length` strip and the decoder family. This pass adds the config-shape
axis: an exact-match URI keeps the upstream line at three tokens, so an attacker query alone
executes, with no percent-encoding and no second request.

RCE is **RCE on the upstream host**. Driven on the compiled release with a strict peer that
echoes the line verbatim plus a token count and fires `sh` only on an exact 3-token target.
`GET /hello.txt` static control precedes the payloads.

## Audit narrative

The upstream target is `l.uri.empty()?r.target:l.uri+path.substr(l.path.size())+query`
(`line 67 (substr)`). On an exact location match the remainder is empty, the URI stands
alone, and the query concatenates directly: `GET /api?cmd=whoami` emits
`GET /exec?cmd=whoami HTTP/1.1`, three tokens. A strict reader executes `whoami`; bare `GET
/api` executes `id`.

This is the encoding-free form of the primitive on this build, and it needs only one request
even on a build whose `Connection` handling is otherwise lossy.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | An exact-match URI leaves the configured exec route as the whole token 1, so an attacker query alone executes a chosen command with no encoding | line 67 (`substr`) | `evidence/e61_exact.log` |

## Findings

### SEC-001 — chosen command in three tokens

`GET /api?cmd=whoami` → `GET /exec?cmd=whoami HTTP/1.1`, three tokens, exec `whoami`, body
`mouse9911`. Bare `GET /api` → `GET /exec HTTP/1.1`, exec `id`. Precondition: `proxy_pass` URI
naming the route with no trailing space, an exact location match, and a strict 3-token reader.
The attacker supplies only a query string.

## Artifact index

- `evidence/e61_exact.log` — control and both 3-token exec lines

## Limitations

- One build.
- Needs an exact match and a strict reader; both stated.
- Upstream-side RCE only; no memory-safety work.
