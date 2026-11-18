# Security audit — run f2b3415b — release/000001 (round 7, lane B)

The upstream target is rebuilt as `configured prefix + path.substr(<config length>) + query`.
The **length is config text**; the **string it indexes is the decoded path**. Nothing reconciles
the two, so a path whose decoded length equals the prefix length slices to nothing and the target
is the destination alone. That reaches the executing route with no `%` and no space in the
client target.

Execution is on the **upstream host** (`sh -c` on the exact token `/exec`).

## Audit narrative

Lane config: proxy_prefix=/api on the proxied location.

Control `GET /hello.txt` → 200 on the same config. Payload `GET /apiexec?cmd=whoami` → upstream
`GET /exec?cmd=whoami HTTP/1.1`, token 2 exactly `/exec`, command executed. No percent byte appears in the client
target, so no decode is relied on. The equal-length form is the only one that lands: a shorter
path fails routing because the location is selected on the same decoded string.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The slice length is config-derived but indexes the decoded path, so an equal-length path emits the destination alone and reaches the exec route with zero encoding | line 87 (`startup`) | `evidence/poc.log`, `evidence/matrix.log` |

## Findings

### SEC-001 — equal-length slice boundary

```
GET /apiexec?cmd=whoami
```

Upstream receives `GET /exec?cmd=whoami HTTP/1.1` (3 whitespace tokens). Client receives 200 with the executed output.
Precondition: a proxied location whose configured prefix the request path can exactly consume.
Severity high: unauthenticated, single request, deterministic, reproduces cold.

## Artifact index

- `evidence/poc.log` — control then payload, with the captured upstream line and exec verdict
- `evidence/matrix.log` — the shape matrix for the build, including the off-by-N controls

## Limitations

- RCE is on the upstream host; nothing executes locally.
- With a prefix/suffix that do not coincide the emitted target keeps the prefix and a decoded
  separator is still needed; that weaker axis is in the matrix log.
