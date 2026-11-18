# Security audit — run 063b0d5e — release/000002 (round 8, lane G)

Ingress framing grammar, driven one shape at a time. Release source pulled from the tag and
diffed against the staged copy: identical, so the cited line is the shipped line.

All RCE is RCE on the **upstream host**; the proxy runs no CGI.

## Audit narrative

Control first on the same config, with a byte-identical control/payload line treated as a no-op.
The matrix then covered request-line delimiter shapes (double space, tab, leading and trailing
space, empty target, empty method), line endings (LF-only, CR-only, mixed), obs-fold, and header
shapes (space before colon, no space, double space, uppercase, underscore name, raw tab in value,
empty value, 40 duplicates).

This build is negative for the delimiter shapes themselves: an explicit find(' ') plus a no-further-space guard rejects a second space, and token(method) rejects TAB, so every odd delimiter form is a 400. The shift is one step later: the upstream target is rebuilt from the decoded path, so %20 survives as a raw space and the upstream split() sees four tokens. Control /exec/exec?cmd=whoami gives a three-token line; /exec/exec%20?cmd=whoami gives GET /exec ?cmd=whoami, four tokens. Precondition: a rewriting proxy_pass, unauthenticated single request.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A decoded space inside a rewritten proxy_pass target becomes a raw space in the upstream request line, four upstream tokens, while the ingress delimiter count stays strict | line 58 (`string upath=loc->uri.empty()`) | `evidence/ev_r8_G_063_ctl_exec.ev` `evidence/ev_r8_G_063_F2_pct20_prefix.ev` `evidence/ev_r8_G_063_DBL.ev` `evidence/ev_r8_G_063_TAB.ev` `evidence/ev_r8_G_063_FOLD.ev` |

## Findings

### SEC-001 — A decoded space inside a rewritten proxy_pass target becomes a raw space in the upstream request line, four upstream tokens, while the ingress delimiter count stays strict

This build is negative for the delimiter shapes themselves: an explicit find(' ') plus a no-further-space guard rejects a second space, and token(method) rejects TAB, so every odd delimiter form is a 400. The shift is one step later: the upstream target is rebuilt from the decoded path, so %20 survives as a raw space and the upstream split() sees four tokens. Control /exec/exec?cmd=whoami gives a three-token line; /exec/exec%20?cmd=whoami gives GET /exec ?cmd=whoami, four tokens. Precondition: a rewriting proxy_pass, unauthenticated single request.

## Artifact index

- `evidence/ev_r8_G_063_ctl_exec.ev`
- `evidence/ev_r8_G_063_F2_pct20_prefix.ev`
- `evidence/ev_r8_G_063_DBL.ev`
- `evidence/ev_r8_G_063_TAB.ev`
- `evidence/ev_r8_G_063_FOLD.ev`

## Limitations

- Upstream-host execution only; no local executor.
- Verdict is for this release; sibling builds were driven separately.
