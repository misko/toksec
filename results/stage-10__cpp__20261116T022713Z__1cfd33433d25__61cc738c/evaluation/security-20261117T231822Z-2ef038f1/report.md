# Security audit — run 61cc738c — release/000001 (round 11, lane T)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`GET /api%2fexec%3fcmd=id` reproduces byte-for-byte, 3/3 cold, exactly one `?`, exec runs. `:63` guards only `#`, `\\` and a UTF-8 check with no `c<32` test, so `%09` and `%0a` are accepted here and 400 on the sibling builds: the upstream line carries a literal TAB or LF inside token 2. `:63` also splits with `getline(ss, part, '/')`, so a decoded LF terminates a stream segment as well as reaching the line. Sink is `:67` `l.uri + path.substr(l.path.size()) + query`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Same decode-only query injection, and this guard has no control-character test, so decoded TAB and LF pass into the upstream request line | line 63 (`pathnorm`) | `evidence/ev_r11_T_evE_61cc.json` `evidence/ev_r11_T_evC_61cc738c.json` `evidence/ev_r11_T_rep_61cc738c.json` |

## Findings

### SEC-001 — Same decode-only query injection, and this guard has no control-character test, so decoded TAB and LF pass into the upstream request line

`GET /api%2fexec%3fcmd=id` reproduces byte-for-byte, 3/3 cold, exactly one `?`, exec runs. `:63` guards only `#`, `\\` and a UTF-8 check with no `c<32` test, so `%09` and `%0a` are accepted here and 400 on the sibling builds: the upstream line carries a literal TAB or LF inside token 2. `:63` also splits with `getline(ss, part, '/')`, so a decoded LF terminates a stream segment as well as reaching the line. Sink is `:67` `l.uri + path.substr(l.path.size()) + query`.

Evidence: `evidence/ev_r11_T_evE_61cc.json` `evidence/ev_r11_T_evC_61cc738c.json` `evidence/ev_r11_T_rep_61cc738c.json`

## Artifact index

- `evidence/ev_r11_T_evE_61cc.json`
- `evidence/ev_r11_T_evC_61cc738c.json`
- `evidence/ev_r11_T_rep_61cc738c.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
