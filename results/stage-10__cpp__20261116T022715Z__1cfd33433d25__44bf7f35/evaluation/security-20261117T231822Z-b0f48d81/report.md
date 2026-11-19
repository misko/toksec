# Security audit — run 44bf7f35 — release/000001 (round 11, lane T)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`GET /api%2fexec%3fcmd=id` is 200 with exactly one `?` upstream, 3/3 cold, exec runs. With `location /apiZ/exec` and `/apiZ%2fexec%3fcmd=id` the decoded `?` falls before the `min()` cut and is dropped, leaving `GET /apiZ%2fexec%20?cmd=id` — exec target present but no `exec` path token and only `query` carrying the command. Two decoded `?` survive as `GET /apiZ%2fexec%20?a?cmd=id` (two `?` on the line), which any first-`?`-only parser mis-splits.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Same guard-versus-sink split, plus a lossy `min()` splice that drops a decoded `?` before the cut and passes two `?` through | line 82 (`normpath`) | `evidence/ev_r11_T_evE_44bf.json` `evidence/ev_r11_T_evZL3_44bf.json` `evidence/ev_r11_T_rep_44bf7f35.json` |

## Findings

### SEC-001 — Same guard-versus-sink split, plus a lossy `min()` splice that drops a decoded `?` before the cut and passes two `?` through

`GET /api%2fexec%3fcmd=id` is 200 with exactly one `?` upstream, 3/3 cold, exec runs. With `location /apiZ/exec` and `/apiZ%2fexec%3fcmd=id` the decoded `?` falls before the `min()` cut and is dropped, leaving `GET /apiZ%2fexec%20?cmd=id` — exec target present but no `exec` path token and only `query` carrying the command. Two decoded `?` survive as `GET /apiZ%2fexec%20?a?cmd=id` (two `?` on the line), which any first-`?`-only parser mis-splits.

Evidence: `evidence/ev_r11_T_evE_44bf.json` `evidence/ev_r11_T_evZL3_44bf.json` `evidence/ev_r11_T_rep_44bf7f35.json`

## Artifact index

- `evidence/ev_r11_T_evE_44bf.json`
- `evidence/ev_r11_T_evZL3_44bf.json`
- `evidence/ev_r11_T_rep_44bf7f35.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
