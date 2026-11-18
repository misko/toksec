# Security audit — run ae021893 — release/000001 (round 10, lane O)

Shape of the request target around a non-`/` prefix: `..` in prefix position, absolute-form, and
multi-segment or doubled-slash targets. Release source read from the tag, byte-identical to the
staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy never executes.

## Audit narrative

Control first on every config, then one hex-exact request per shape with `ss -ltnp` before each
port. The sink is the upstream request line: the proxy splices the decoded path after the
location's proxy URI, so a `..` that survives decoding travels to the peer verbatim. Whether that
matters depends only on where the build runs its guard.

One absolute-form request per build, control first: `GET http://alpha.test/api%2fexec%20?cmd=id HTTP/1.1` is 400 on all seventeen audited builds and the upstream is never contacted. The `rfind("http://",0)` in two builds is the proxy_pass parser, not the request path.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | no | informational | Absolute-form request targets are answered 400 at the decoder's first-byte `/` test, so the authority never dispatches | line 51 (`parseheader`) | `evidence/ev_r10_O_3aeb255d3d7f_ae021893_O2_abs.hex` |

## Findings

### SEC-001 — Absolute-form request targets are answered 400 at the decoder's first-byte `/` test, so the authority never dispatches

The exact-`/` test is the first statement of the decoder, before any prefix match, so an absolute-form target never reaches dispatch. Probed extras on 063b0d5e (authority disagreeing with `Host`, no `Host`, `:port` authority, userinfo) are all 400 too.

Evidence: `evidence/ev_r10_O_3aeb255d3d7f_ae021893_O2_abs.hex`

## Artifact index

- `evidence/ev_r10_O_3aeb255d3d7f_ae021893_O2_abs.hex`

## Limitations

- Upstream-host execution only.
- Needs nothing beyond a proxied prefix location.
