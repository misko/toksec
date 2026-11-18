# Security audit — run 8d5ff1f2 — release/000002 (round 7, lane D)

Static file-layer pass. The one real defect is on the **301 `Location` build**: the decoded path
is concatenated into the header block while the decoder rejects only NUL and backslash, so CR and
LF survive into the response head.

This is a **response-splitting primitive against the client**, not server-side execution. The
build has no upstream, so nothing executes on the host.

## Audit narrative

`pathnorm` (line 77) guards `if(!c||c=='\\')return 400` and nothing else, so every other byte
including CR (0x0d) and LF (0x0a) is admitted into the decoded path. The 301 sink (line 90) does
`response(c,301,"Location: "+path+"/"+query+...)`, and `response()` concatenates the fields
string into the head verbatim. Everything after the first CRLF therefore becomes a header.

Observed, each a single request:

- `GET /hdr%0d%0aX-Inject:%20yes` → `Location: /hdr` then a real `X-Inject: yes/` line.
- `GET /x%0d%0aX-Own:%20pwned` on a 2-byte file → extra header, body still exactly `AB`.
- `GET /ck3%0d%0aSet-Cookie:%20sid=pwned` → a live `Set-Cookie` that a browser stores.
- `GET /split%0d%0a%0d%0aFORGED` → head ends early; the genuine tail becomes body.
- `GET /cl%0d%0aContent-Length:%20999` → duplicate `Content-Length`; curl 8.18.0 fails with
  `Invalid Content-Length: value`.

Caveat, stated: the 301 only fires for a slashless directory, so the injected line always has the
appended `/` (and any query) glued on (`X-Inject: yes/`). Keep the injected token ending in `:`, or
put it after a `%3f`, to absorb the slash.

Controls: `GET /hello.txt` → 200, `GET /ten.txt` with `Range: bytes=2-4` → exactly `234`. Range on
a 0-byte file is 416 `bytes */0`; symlinks are refused (this build uses `O_NOFOLLOW` per component,
so even a symlinked root 404s); a hard link serves; `..` 403.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The 301 `Location` is concatenated from the decoded path while the decoder admits CR and LF, so the response head can be split and headers forged | line 77 (`pathnorm`) guard, sink line 90 (`response`) | `evidence/hdrinj.log`, `evidence/crlfuf.log`, `evidence/loc2.log`, `evidence/loc_decode.log` |

## Findings

### SEC-001 — response header injection through Location

```
GET /ck3%0d%0aSet-Cookie:%20sid=pwned HTTP/1.1
Host: alpha.test
Connection: close
```

Client head becomes:

```
HTTP/1.1 301 Moved Permanently
Location: /ck3
Set-Cookie: sid=pwned/
Content-Length: 0
Connection: keep-alive
```

Precondition: attacker controls the path on a build whose decoder omits the C0 check, and a
directory whose name carries the bytes. Value is client-side (cookie, cache, header confusion);
a full second response is injectable as body, not as a true second response.

## Artifact index

- `evidence/hdrinj.log` — the four-case injection set with raw head bytes and the curl cross-check
- `evidence/crlfuf.log` — the CRLF matrix across all six decoders, showing only this build passes
- `evidence/loc2.log` — the Set-Cookie and forged-second-response cases
- `evidence/loc_decode.log` — the decoded-vs-raw Location comparison
- `evidence/range.log` — the Range table for parity

## Limitations

- No upstream, so no code execution is involved.
- The appended slash lands in every injected value.
