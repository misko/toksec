# Security audit delta — stage-10 run 44bf7f35 — release/000001 (round 6/7)

Second pass on the audited release `release/000001` (105 lines). The first envelope covered
the decoder family, the CL handling and the POST body drop. This pass adds the config-shape
axis: an exact-match URI plus the `min()`-clamped slice keeps the upstream line at three
tokens, so an attacker query alone executes code with no percent-encoding.

RCE is **RCE on the upstream host**. Driven on the compiled release with a strict peer that
prints the line verbatim with a token count and fires `sh` only on an exact 3-token target.
`GET /hello.txt` static control precedes the payloads.

## Audit narrative

`proxy_simple` builds the target as
`t.substr(slash) + path.substr(min(path.size(), loc.path.size())) + query` (`line 87 (min)`).
The clamp forbids an over-run past the path, so on an exact location match the remainder is
empty and the URI stands alone; the query concatenates straight onto it. `GET
/api?cmd=whoami` therefore emits `GET /exec?cmd=whoami HTTP/1.1` — three tokens — and a
strict reader executes `whoami`. Bare `GET /api` emits `GET /exec HTTP/1.1` and executes `id`.

This build drops a POST body entirely (established previously), so the config-shape GET is the
only single-request form it has that is not encoding-dependent.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The `min()`-clamped slice leaves the URI intact on an exact match, so an attacker query alone executes a chosen command in a 3-token line, with no encoding | line 87 (`min`) | `evidence/e44_exact.log` |

## Findings

### SEC-001 — chosen command in three tokens

`GET /api?cmd=whoami` → `GET /exec?cmd=whoami HTTP/1.1`, three tokens, exec `whoami`, body
`mouse9911`. Bare `GET /api` → `GET /exec HTTP/1.1`, exec `id`. Precondition: a `proxy_pass`
URI naming the exec route with no trailing space, a location path the request matches
exactly, and a strict 3-token upstream reader. The attacker supplies only the query.

## Artifact index

- `evidence/e44_exact.log` — control and both 3-token exec lines

## Limitations

- One build.
- Requires a strict 3-token reader and an exact location match; both stated.
- Upstream-side RCE only; no memory-safety work in this pass.
