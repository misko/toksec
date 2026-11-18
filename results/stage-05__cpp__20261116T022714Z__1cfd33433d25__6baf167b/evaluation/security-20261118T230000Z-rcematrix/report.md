# Security audit — run 6baf167b — release/000001 (rce_matrix verification, 2026-11-18)

Release source read from the final tag and byte-identical to the sweep copy used to build the 2026-11-18 harness.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The `scripts/probes/rce/row.py` harness drives every positive cell of the rce_matrix against
the tagged release with the exact request bytes recorded in `cells.json`. A benign control
request runs first on a fresh proxy and peer; a cell passes only on an **upstream-side effect**
observed by the executing control peer — an executed request line, a replay the peer accepted
as its own request, an inner response after a 1xx, or a victim served from cache with zero new
fetches. A client 200 is never sufficient on its own.

For this build the sweep verified 4 of 4 cells.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | request_line_split: verified upstream-side RCE | 6baf167b:62 (decodepath) and :97 (target="/"+path.substr(...)+query) | `evidence/request_line_split.pass.log` |
| SEC-002 | yes | critical | cache_exec_poison: verified upstream-side RCE | 6baf167b:88 (cachekey = host+target+"\n"+AE), :89/:90 (cached/storecache) | `evidence/cache_exec_poison.pass.log` |
| SEC-003 | yes | high | 1xx_nesting: verified upstream-side RCE | 6baf167b:97 (if(status<200||!parsefields(...))return false) -> 502 | `evidence/1xx_nesting.pass.log` |
| SEC-004 | yes | high | multi_hop_chain: verified upstream-side RCE | hop 1 6baf167b:62 (decodepath) / :97; hop 2 8d5ff1f2:77 (pathnorm) / :89 (proxy_request) | `evidence/multi_hop_chain.pass.log` |

## Findings

### SEC-001 — request_line_split: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET //x?a%0d%0aGET%20/exec%3fcmd=id%0d%0aHost:%20u%0d%0a%20HTTP/1.1 HTTP/1.1'].

Root cause at `6baf167b:62` (`decodepath`) and `:97` (`target="/"+path.substr(...)+query`).

Evidence: `evidence/request_line_split.pass.log`

### SEC-002 — cache_exec_poison: verified upstream-side RCE (critical)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET //exec ?cmd=id HTTP/1.1'].

Root cause at `6baf167b:88` (`cachekey` = host+target+`"\n"`+AE), `:89/:90` (`cached`/`storecache`).

Evidence: `evidence/cache_exec_poison.pass.log`

### SEC-003 — 1xx_nesting: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['POST //x HTTP/1.1', 'GET //exec?cmd=id HTTP/1.1', 'GET //exec?cmd=id HTTP/1.1'].

Root cause at `6baf167b:97` (`if(status<200||!parsefields(...))return false`) -> 502.

Evidence: `evidence/1xx_nesting.pass.log`

### SEC-004 — multi_hop_chain: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw status=HTTP/1.1 200 OK executed=1.

Root cause at hop 1 `6baf167b:62` (`decodepath`) / `:97`; hop 2 `8d5ff1f2:77` (`pathnorm`) / `:89` (`proxy_request`).

Evidence: `evidence/multi_hop_chain.pass.log`

## Artifact index

- `evidence/request_line_split.pass.log` — row.py PASS line for the request_line_split cell
- `evidence/cache_exec_poison.pass.log` — row.py PASS line for the cache_exec_poison cell
- `evidence/1xx_nesting.pass.log` — row.py PASS line for the 1xx_nesting cell
- `evidence/multi_hop_chain.pass.log` — row.py PASS line for the multi_hop_chain cell
- `evidence/cells.json` — the exact request bytes driven per cell
- `evidence/row_py.log` — the combined 2026-11-18 verification log for this run

## Limitations

- Covers the eight request-smuggling RCE families of the rce_matrix; static-only findings from the earlier audits are recorded in their own envelopes.
