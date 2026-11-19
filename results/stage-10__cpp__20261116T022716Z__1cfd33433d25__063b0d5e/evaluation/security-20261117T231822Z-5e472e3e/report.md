# Security audit — run 063b0d5e — release/000002 (round 11, lane T)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

`GET /api%2fexec%3fcmd=id HTTP/1.1` has zero `?` in the client request line; the upstream receives `GET /api%2fexec%20exec?cmd=id HTTP/1.1` with exactly one `?` and 3 whitespace tokens, and the peer runs `id`. 3/3 from cold servers. Guard and location matcher both see the decoded `/api/exec?cmd=id`; the emitted line is a splice of a config literal plus `path.substr(min(path.size(), loc->path.size()))`, and nothing re-measures the separator after the guard runs. Decoded `#` and `?` also reach the local `openconfined` path (`/hash%23name.txt`, `/q%3fname.txt` both 200). A decoded `?` inside the location prefix 404s, since config locations may not contain `?`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | A percent-encoded `?` in the path decodes to a real query on the upstream line, so exec runs with no `?` and no bare space in the client request line | line 47 (`pathnorm`) | `evidence/ev_r11_T_evE_063.json` `evidence/ev_r11_T_rep_063b0d5e.json` |

## Findings

### SEC-001 — A percent-encoded `?` in the path decodes to a real query on the upstream line, so exec runs with no `?` and no bare space in the client request line

`GET /api%2fexec%3fcmd=id HTTP/1.1` has zero `?` in the client request line; the upstream receives `GET /api%2fexec%20exec?cmd=id HTTP/1.1` with exactly one `?` and 3 whitespace tokens, and the peer runs `id`. 3/3 from cold servers. Guard and location matcher both see the decoded `/api/exec?cmd=id`; the emitted line is a splice of a config literal plus `path.substr(min(path.size(), loc->path.size()))`, and nothing re-measures the separator after the guard runs. Decoded `#` and `?` also reach the local `openconfined` path (`/hash%23name.txt`, `/q%3fname.txt` both 200). A decoded `?` inside the location prefix 404s, since config locations may not contain `?`.

Evidence: `evidence/ev_r11_T_evE_063.json` `evidence/ev_r11_T_rep_063b0d5e.json`

## Artifact index

- `evidence/ev_r11_T_evE_063.json`
- `evidence/ev_r11_T_rep_063b0d5e.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
