# Security audit — run 6baf167b — release/000001 (round 10, lane O)

Shape of the request target around a non-`/` prefix: `..` in prefix position, absolute-form, and
multi-segment or doubled-slash targets. Release source read from the tag, byte-identical to the
staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy never executes.

## Audit narrative

Control first on every config, then one hex-exact request per shape with `ss -ltnp` before each
port. The sink is the upstream request line: the proxy splices the decoded path after the
location's proxy URI, so a `..` that survives decoding travels to the peer verbatim. Whether that
matters depends only on where the build runs its guard.

Same positive, cited at the dispatch site so the fix location is unambiguous: the guard would have to move to the decoder, or the proxy branch must run it.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | no | low | Dispatch order is the root cause: the proxy branch is taken before `local()` can run the guard | line 109 (`c.req.proxy`) | `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex` |

## Findings

### SEC-001 — Dispatch order is the root cause: the proxy branch is taken before `local()` can run the guard

`:109` tests `c.req.proxy` and enters the proxy path without any `..` check; `local()` at `:80` is only reached when the location is not a proxy. Moving the check into the decode (as the other sixteen builds do) closes it.

Evidence: `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex`

## Artifact index

- `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex`

## Limitations

- Upstream-host execution only.
- Same build; the defect is the ordering, not the guard expression, which is correct.
