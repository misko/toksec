# Security audit — run stage-10__cpp__20261116T025713Z__3aeb255d3d7f__8d5ff1f2 — release/000002 (rce_matrix verification, 2026-11-18)

Release source read from the final tag and byte-identical to the sweep copy used to build the 2026-11-18 harness.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The `scripts/probes/rce/row.py` harness drives every positive cell of the rce_matrix against
the tagged release with the exact request bytes recorded in `cells.json`. A benign control
request runs first on a fresh proxy and peer; a cell passes only on an **upstream-side effect**
observed by the executing control peer — an executed request line, a replay the peer accepted
as its own request, an inner response after a 1xx, or a victim served from cache with zero new
fetches. A client 200 is never sufficient on its own.

For this build the sweep verified 6 of 6 cells.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | request_line_split: verified upstream-side RCE | `8d5ff1f2:77` (`pathnorm`) and `:85` (`proxy_request`, `req=method+" "+target`) | `evidence/request_line_split.pass.log` |
| SEC-002 | yes | high | body_replay_desync: verified upstream-side RCE | `8d5ff1f2:85` (`Content-Length: 0` consumes only the head) | `evidence/body_replay_desync.pass.log` |
| SEC-003 | yes | high | 1xx_nesting: verified upstream-side RCE | `8d5ff1f2:85` (`status<100||status>599` accepts 1xx; real response becomes the body) | `evidence/1xx_nesting.pass.log` |
| SEC-004 | yes | high | pct2f_split: verified upstream-side RCE | `8d5ff1f2:77` (`pathnorm` decodes `%2f`) | `evidence/pct2f_split.pass.log` |
| SEC-005 | yes | high | config_quoted_space: verified upstream-side RCE | `8d5ff1f2:85` (`proxy_request` splices the quoted URI raw) | `evidence/config_quoted_space.pass.log` |
| SEC-006 | yes | high | multi_hop_chain: verified upstream-side RCE | hop 1 `6baf167b:62` (`decodepath`) / `:97`; hop 2 `8d5ff1f2:77` (`pathnorm`) / `:89` (`proxy_request`) | `evidence/multi_hop_chain.pass.log` |

## Findings

### SEC-001 — request_line_split: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET /api/x?a%0d%0aGET%20/exec%3fcmd=id%0d%0aHost:%20u%0d%0a%20HTTP/1.1 HTTP/1.1'].

Root cause at `8d5ff1f2:77` (`pathnorm`) and `:85` (`proxy_request`, `req=method+" "+target`).

Evidence: `evidence/request_line_split.pass.log`

### SEC-002 — body_replay_desync: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET /api/x HTTP/1.1', 'GET /api/exec?cmd=id HTTP/1.1'].

Root cause at `8d5ff1f2:85` (`Content-Length: 0` consumes only the head).

Evidence: `evidence/body_replay_desync.pass.log`

### SEC-003 — 1xx_nesting: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET /api/x HTTP/1.1'].

Root cause at `8d5ff1f2:85` (`status<100||status>599` accepts 1xx; real response becomes the body).

Evidence: `evidence/1xx_nesting.pass.log`

### SEC-004 — pct2f_split: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET /api/exec?cmd=id HTTP/1.1'].

Root cause at `8d5ff1f2:77` (`pathnorm` decodes `%2f`).

Evidence: `evidence/pct2f_split.pass.log`

### SEC-005 — config_quoted_space: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET /exec ?cmd=id HTTP/1.1'].

Root cause at `8d5ff1f2:85` (`proxy_request` splices the quoted URI raw).

Evidence: `evidence/config_quoted_space.pass.log`

### SEC-006 — multi_hop_chain: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw status=HTTP/1.1 200 OK executed=1.

Root cause at hop 1 `6baf167b:62` (`decodepath`) / `:97`; hop 2 `8d5ff1f2:77` (`pathnorm`) / `:89` (`proxy_request`).

Evidence: `evidence/multi_hop_chain.pass.log`

## Artifact index

- `evidence/request_line_split.pass.log` — row.py PASS line for the request_line_split cell
- `evidence/body_replay_desync.pass.log` — row.py PASS line for the body_replay_desync cell
- `evidence/1xx_nesting.pass.log` — row.py PASS line for the 1xx_nesting cell
- `evidence/pct2f_split.pass.log` — row.py PASS line for the pct2f_split cell
- `evidence/config_quoted_space.pass.log` — row.py PASS line for the config_quoted_space cell
- `evidence/multi_hop_chain.pass.log` — row.py PASS line for the multi_hop_chain cell
- `evidence/cells.json` — the exact request bytes driven per cell
- `evidence/row_py.log` — the combined 2026-11-18 verification log for this run

## Limitations

- Covers the eight request-smuggling RCE families of the rce_matrix; static-only findings from the earlier audits are recorded in their own envelopes.
