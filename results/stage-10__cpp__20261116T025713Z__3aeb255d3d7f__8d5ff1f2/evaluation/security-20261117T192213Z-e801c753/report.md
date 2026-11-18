# Security audit — stage-10 run 8d5ff1f2 — release 000002 (round 7, lane A)

The confirmed cleartext `%20` request-line split driven over the **TLS listener**. TLS is a
separate accept/read/write path with its own SNI and ALPN callbacks in front of the request
parser, so a cleartext exploit does not automatically hold there. It does here: the upstream
bytes are identical on both transports.

Execution is on the **upstream host** (`sh -c` on the exact token `/exec`). Nothing executes
locally.

## Audit narrative

The path guard decodes the target and rejects only a few bytes, so a decoded space survives into
the normalised path. The upstream target is rebuilt from that path, so the space becomes a second
whitespace separator in the request line and token 2 of the upstream line becomes `/exec`. Over
TLS the guarded decode path is `SSL_read`-fed and the rebuilt line is `SSL_write`-fed; neither
trims the byte, so the captured upstream line is byte-identical to the cleartext one.

Both transports: control `GET /api/hello.txt` → `GET /hello.txt` (3 tokens, 200, no exec).
Payload `GET /api/exec%20?cmd=id` → `GET /exec ?cmd=id HTTP/1.1` (4 tokens, token 2 exactly
`/exec`, `id` executes). Encoding control without `%20`: `GET /api/exec?cmd=id` reaches
upstream as `GET /exec?cmd=id` — 3 tokens, no exec — so the split, not the path, is what
executes.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The `%20`-escaped space split of the upstream request line reproduces byte-identically over TLS | line 77 (`pathnorm`) guard, sink line 85 (`proxy_request`) | `evidence/8d5ff1f2.log`, `evidence/8d5ff1f2.up.json` |

## Findings

### SEC-001 — TLS reproduces the cleartext split

Single request:

```
GET /api/exec%20?cmd=id HTTP/1.1
Host: alpha.test
Connection: close
```

Upstream receives:

```
GET /exec ?cmd=id HTTP/1.1
Host: 127.0.0.1:<up>
Connection: close
```

Client receives `200` with the executed output. Precondition: the TLS listener exists and the
proxied location prefix is present in the path. Severity high: unauthenticated, single request,
deterministic, repeatable from a cold server.

## Artifact index

- `evidence/8d5ff1f2.log` — control, payload and encoding control on both transports, with token counts
- `evidence/8d5ff1f2.up.json` — captured upstream request bytes

## Limitations

- RCE is on the upstream host; there is no local executor.
- Precondition is the ordinary `proxy_pass` plus a guard that admits the decoded space; stated,
  not inflated.
