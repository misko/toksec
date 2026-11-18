# Security audit — run 29d05850 — release/000002 (round 8, lane G)

Ingress framing grammar, driven one shape at a time. Release source pulled from the tag and
diffed against the staged copy: identical, so the cited line is the shipped line.

All RCE is RCE on the **upstream host**; the proxy runs no CGI.

## Audit narrative

Control first on the same config, with a byte-identical control/payload line treated as a no-op.
The matrix then covered request-line delimiter shapes (double space, tab, leading and trailing
space, empty target, empty method), line endings (LF-only, CR-only, mixed), obs-fold, and header
shapes (space before colon, no space, double space, uppercase, underscore name, raw tab in value,
empty value, 40 duplicates).

The request line is parsed with istringstream extraction, which collapses space runs and treats TAB as a separator, and the only grammar check is the three-token extraction plus token(method). So GET  /hello.txt, TAB-delimited, leading-space and trailing-space forms are all accepted 200 and re-emitted as a normal single-space line: accepted but identical, negative for smuggling. The delta appears only when proxy_pass carries a URI and the target is rebuilt from the decoded path, where a %20 becomes a raw space and the upstream split() re-cuts the line to four tokens. On the plain form the RCE survives; when the exec route is not the first segment (GET /exec/a%20exec?cmd=whoami to GET /a exec?cmd=whoami) the displaced query lands as token 4 and EXEC comes back empty, so an accepted shape silently kills a working RCE. Precondition: a rewriting proxy_pass.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | The istringstream parser accepts double space, tab, leading and trailing space but normalises them back to three tokens, so a decoded space in a rewritten proxy_pass target is what actually shifts the downstream token count | line 50 (`istringstream ss(lines[0])`) | `evidence/ev_r8_G_29d_ctl_exec.ev` `evidence/ev_r8_G_29d_F2_pct20_prefix.ev` `evidence/ev_r8_G_29d_DBL.ev` `evidence/ev_r8_G_29d_TAB.ev` `evidence/ev_r8_G_29d_HSP.ev` `evidence/ev_r8_G_29d_FOLD.ev` `evidence/ev_r8_G_29d_LEAD.ev` `evidence/ev_r8_G_29d_TRAIL.ev` |

## Findings

### SEC-001 — The istringstream parser accepts double space, tab, leading and trailing space but normalises them back to three tokens, so a decoded space in a rewritten proxy_pass target is what actually shifts the downstream token count

The request line is parsed with istringstream extraction, which collapses space runs and treats TAB as a separator, and the only grammar check is the three-token extraction plus token(method). So GET  /hello.txt, TAB-delimited, leading-space and trailing-space forms are all accepted 200 and re-emitted as a normal single-space line: accepted but identical, negative for smuggling. The delta appears only when proxy_pass carries a URI and the target is rebuilt from the decoded path, where a %20 becomes a raw space and the upstream split() re-cuts the line to four tokens. On the plain form the RCE survives; when the exec route is not the first segment (GET /exec/a%20exec?cmd=whoami to GET /a exec?cmd=whoami) the displaced query lands as token 4 and EXEC comes back empty, so an accepted shape silently kills a working RCE. Precondition: a rewriting proxy_pass.

## Artifact index

- `evidence/ev_r8_G_29d_ctl_exec.ev`
- `evidence/ev_r8_G_29d_F2_pct20_prefix.ev`
- `evidence/ev_r8_G_29d_DBL.ev`
- `evidence/ev_r8_G_29d_TAB.ev`
- `evidence/ev_r8_G_29d_HSP.ev`
- `evidence/ev_r8_G_29d_FOLD.ev`
- `evidence/ev_r8_G_29d_LEAD.ev`
- `evidence/ev_r8_G_29d_TRAIL.ev`

## Limitations

- Upstream-host execution only; no local executor.
- Verdict is for this release; sibling builds were driven separately.
