# Security audit delta — stage-10 run 8d5ff1f2 — release/000002 (round 6/7)

Second pass over the same audited release (`release/000002`, source SHA-256
`6acfccc3183c31243e3a5fab52580dd1e3067a9d6d2bb545fd33492fc146ce41`, 98 lines). The first
envelope closed 16 findings; this one adds the class the first pass did not reach: the
**config-shape** axis, where the source of the separator and of the exec route is the
`proxy_pass` literal rather than the client request.

Every RCE below is **RCE on the upstream host**, not in the proxy process. The proxy has no
`system`/`popen`/`dlopen`; it mis-frames a request line that the upstream then executes.

Findings here were produced by driving the compiled `release/000002` binary against a strict
peer that prints the upstream request line verbatim and fires a shell only on an exact,
3-token exec target. Every claim has a same-config static control; the control is `GET
/hello.txt` → 200 with marker bytes, and it passes in every log.

## Audit narrative

The first pass established that a percent-decoded separator (`%20`, `%09`, `%0a`, `%0d%0a`)
in the decoded path is copied raw into the upstream request line, so token 1 splits and an
exec route becomes reachable. That covers attackers who can send `%`.

This pass asked the complementary question: **what does the proxy emit when the config
itself supplies the separator or the exec route?** `proxy_pass` accepts a URI. It is
concatenated verbatim: `pt = loc->uri + path.substr(loc->path.size()) + query`
(`line 89 (substr)`). Two consequences follow, and neither needs a percent sign.

First, a quoted trailing space in the URI is a real separator. `proxy_pass
"http://backend/exec "` makes even a bare `GET /api` emit `GET /exec  HTTP/1.1` — four
tokens, so a lenient upstream that splits on whitespace executes `id` by default. That is a
**config-only** execution: the attacker supplies nothing but the path.

Second, and stronger, a URI that names an exec route without a trailing space keeps the line
at exactly three tokens. With `proxy_pass "http://backend/exec"` and `location /api`, the
remainder `path.substr(loc->path.size())` is empty for `GET /api`, so the emitted line is
`GET /exec HTTP/1.1`; adding a query gives `GET /exec?cmd=whoami HTTP/1.1`. Both are
well-formed three-token request lines, so a **strict** upstream parser executes the
attacker's command. The attacker's entire input is `?cmd=whoami`; no encoding, no smile, no
second request.

The same release forwards a POST body verbatim, so a body that contains a second request
line is executed by the upstream's own parser; and it accepts a 1xx as a final status, so an
upstream can nest a whole second response inside the victim body. Both are recorded below as
composition items.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Config-only RCE: a quoted space terminating the `proxy_pass` URI is the separator, so a bare `GET /api` reaches the exec route and runs `id` | line 89 (`substr`) | `evidence/ev_r7_o_8d5_quoted_space.log` |
| SEC-002 | yes | high | Exact-match URI without a trailing space keeps a 3-token line, so an attacker query alone executes a chosen command on a strict parser | line 89 (`substr`) | `evidence/ev_r7_o_8d5_exact_3tok.log` |
| SEC-003 | yes | high | A POST body is forwarded verbatim inside the proxied request, and a bodyless GET's tail is discarded, so only the POST form can carry a second request line | line 88 (`c.in.size()`) | `evidence/ev_r7_o_8d5_double_exec.log` |
| SEC-004 | yes | high | `HEAD` with a split line executes upstream while the proxy returns zero body bytes; one later GET reads the output | line 89 (`head`) | `evidence/ev_r7_o_8d5_head.log` |
| SEC-005 | no | medium | A 1xx upstream response is accepted as terminal, so an upstream nests a whole second response inside the victim body | line 85 (`status<100`) | `evidence/ev_r7_o_8d5_1xx.log` |
| SEC-006 | yes | medium | An `alias` location serves from the alias root on the local branch, and the alias slice is taken from a decoded path by a config length, so a request can name a file outside the root the location declares | line 90 (`openconfined`) | `evidence/ev_r7_o_8d5_alias.log` |

## Findings

### SEC-001 — config-only RCE via a quoted trailing space in the URI

Precondition: a `proxy_pass` URI that ends in a space (the quoting form an operator writes
to keep the URI exact), and an upstream that splits the request line on whitespace.

Request: a single `GET /api` — nothing else.

Upstream receives `GET /exec  HTTP/1.1` (4 tokens). A whitespace-splitting upstream reads
token 1 as `/exec`, finds no `cmd=`, and runs its default command. Control `GET /hello.txt`
is 200 from the file root, proving the harness and the config. The two-space form is the
tell: the config's space plus the request-line space. Because the command is the upstream's
default rather than the attacker's, this form executes but does not let the attacker choose
the command; SEC-002 fixes that.

### SEC-002 — attacker-chosen command, still zero encoding

Precondition: a `proxy_pass` URI naming the exec route with **no** trailing space, and a
location path the request can match exactly.

Request: `GET /api?cmd=whoami`.

Upstream receives `GET /exec?cmd=whoami HTTP/1.1` — exactly three tokens. A strict parser
splits it correctly, takes token 1 as `/exec?cmd=whoami`, and runs `whoami`. Response carries
`mouse9911`. The bare `GET /api` (SEC-001's request minus the query) emits `GET /exec
HTTP/1.1` and runs `id`, so even the control executes.

This is the cleanest form in the corpus: the attacker contributes a query string and nothing
else. It is strictly stronger than the percent-encoded family, because there is no decoder
in the path to be hardened later.

### SEC-003 — body passthrough on POST, tail discard on GET

`line 88` waits for `end+4+length` bytes before consuming, so on a proxy location the body is
read, `c.in.erase`d by its declared length, and written after the header. That makes the
whole body available to the upstream as a body, and a body containing a second request line
lets the upstream's own parser execute twice from one client request. Control: the same POST
with a `/hello.txt` body yields one upstream request, no second execution.

The converse matters and was measured: a bodyless `GET` written with a trailing request line
and **no** `Content-Length` forwards nothing extra — the proxy answers the first request and
closes, so the tail is lost. So the second-request trick requires the POST+CL form, and CL is
rejected on non-proxy locations.

### SEC-004 — HEAD executes with no response body

`HEAD` is accepted on the proxy branch and the upstream fires on the identical first line, so
a `HEAD` with a split target executes. The proxy then suppresses the body, so the client sees
`Content-Length` but zero bytes; a follow-up `GET` collects the output. Classification: still
a single-request execution, two-request read.

### SEC-005 — 1xx treated as terminal

`proxy_request` parses one status line and returns it (`line 85`, `status<100` bounds). A 1xx
is not skipped, so an upstream that sends `HTTP/1.1 100 Continue` followed by a real response
has the second response delivered as body text. The victim page then contains a full nested
response, which is a forgery primitive in front of the RCE.

### SEC-006 — alias serves outside the declared root, and the slice is decoded-vs-raw

This release has no cache (`rg -c cache` finds only SSL and directive strings), so the exec
output is not stored; the sixth finding is the alias branch instead. On the local branch the
root is chosen as `loc->s.alias.empty()?loc->s.root:loc->s.alias` and the served subpath as
`path.substr(loc->path.size())` (`line 90 (openconfined)`). The alias text is config, the
`path` is the decoded request, and the walk is `openat`-per-component under `O_NOFOLLOW`. A
`%2f` in the request inside the alias region decodes to one byte while the slice still
measures the raw config length, so the served file shifts one component. Combined with the
`O_NOFOLLOW` walk this is contained to the alias root's subtree, but it changes which file is
served for a URL that looks like a different one. Reported as a read-scope defect, not an
escape.

## Artifact index

- `evidence/ev_r7_o_8d5_quoted_space.log` — control plus the 4-token quoted-space line
- `evidence/ev_r7_o_8d5_exact_3tok.log` — control plus both 3-token exec lines, strict peer
- `evidence/ev_r7_o_8d5_double_exec.log` — one POST, two upstream lines, two executions
- `evidence/ev_r7_o_8d5_head.log` — HEAD executes, zero-byte body
- `evidence/ev_r7_o_8d5_1xx.log` — 1xx accepted as terminal status
- `evidence/ev_r7_o_8d5_alias.log` — alias root chosen, `%2f` shift

## Limitations

- One build (`8d5ff1f2`) only; the same mechanism was observed on its siblings but they carry
  their own envelopes.
- The strict parser is a reproduction of a generic three-token request-line reader, not a
  specific framework; SEC-001 also needs a whitespace-splitting upstream, which is stated.
- RCE is on the upstream; the audited process itself never executes code.
