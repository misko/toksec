# Security audit delta — stage-10 run 29d05850 — release/000002 (round 6/7)

Second pass on the audited release `release/000002` (60 lines). The first envelope closed the
decoder-family findings. This pass adds the config-shape axis: the separator and the exec
target can come from the `proxy_pass` literal, so no percent-encoding is needed at all.

All RCE is **RCE on the upstream host**; the proxy has no local exec. Driven on the compiled
release against a strict peer that echoes the upstream line verbatim with a token count and
fires `sh` only on an exact 3-token exec target. A `GET /hello.txt` static control precedes
every payload.

## Audit narrative

The rebuild here is `pt = v.substr(slashpos) + norm.substr(l->path.size()) + query`
(`line 50 (substr)`). The path is decoded and the length is config text.

An exact location match makes the remainder empty and leaves the URI alone, so a query alone
drives the command: `GET /api?cmd=whoami` emits `GET /exec?cmd=whoami HTTP/1.1`, three
tokens, and a strict parser runs `whoami`. A quoted trailing space in the URI instead makes a
bare `GET /api` emit `GET /exec  HTTP/1.1`, four tokens, executing the upstream's default
command. Both need no encoding.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Exact-match URI without a trailing space keeps a 3-token line, so an attacker query alone executes a chosen command on a strict parser | line 50 (`substr`) | `evidence/e29_exact.log` |
| SEC-002 | yes | high | A quoted space in the `proxy_pass` URI is the separator, so a bare `GET /api` executes the upstream default command with no encoding | line 50 (`substr`) | `evidence/e29_qs.log` |

## Findings

### SEC-001 — chosen command in three tokens

`GET /api?cmd=whoami` → upstream `GET /exec?cmd=whoami HTTP/1.1`, exec `whoami`, body
`mouse9911`; bare `GET /api` → `GET /exec HTTP/1.1`, exec `id`. Precondition: a URI naming the
route without a trailing space, and a strict 3-token upstream reader. The attacker supplies
only a query.

### SEC-002 — quoted-space config executes with no query

`GET /api` → `GET /exec  HTTP/1.1`, four tokens, a whitespace-splitting upstream runs `id`.
Precondition: the quoted trailing space plus a whitespace-splitting upstream. Executes, but
the command is the upstream default rather than the attacker's.

## Artifact index

- `evidence/e29_exact.log` — control and the two 3-token exec lines
- `evidence/e29_qs.log` — control and the quoted-space 4-token line

## Limitations

- One build; siblings carry their own envelopes.
- SEC-001 needs a strict reader, SEC-002 a whitespace-splitting one; the precondition differs
  per finding and is stated.
- RCE is upstream-side; no memory-safety work.
