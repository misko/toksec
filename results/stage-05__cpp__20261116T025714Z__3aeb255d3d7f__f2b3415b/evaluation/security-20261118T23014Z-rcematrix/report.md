# Security audit — run stage-05__cpp__20261116T025714Z__3aeb255d3d7f__f2b3415b — release/000001 (rce_matrix verification, 2026-11-18)

Release source read from the final tag and byte-identical to the sweep copy used to build the 2026-11-18 harness.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The `scripts/probes/rce/row.py` harness drives every positive cell of the rce_matrix against
the tagged release with the exact request bytes recorded in `cells.json`. A benign control
request runs first on a fresh proxy and peer; a cell passes only on an **upstream-side effect**
observed by the executing control peer — an executed request line, a replay the peer accepted
as its own request, an inner response after a 1xx, or a victim served from cache with zero new
fetches. A client 200 is never sufficient on its own.

For this build the sweep verified 3 of 3 cells.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | request_line_split: verified upstream-side RCE | `f2b3415b:49` (decode) and `:87` (`startup`, `c->upout=...`) | `evidence/request_line_split.pass.log` |
| SEC-002 | yes | high | body_replay_desync: verified upstream-side RCE | `f2b3415b:87` (`startup`, body never framed back) | `evidence/body_replay_desync.pass.log` |
| SEC-003 | yes | medium | retry_double_exec: verified upstream-side RCE | `f2b3415b:87` (`startup` retry buffer), `FINDING_r13_C.md:49` | `evidence/retry_double_exec.pass.log` |

## Findings

### SEC-001 — request_line_split: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['GET //x?a%0d%0aGET%20/exec%3fcmd=id%0d%0aHost:%20u%0d%0a%20HTTP/1.1 HTTP/1.1'].

Root cause at `f2b3415b:49` (decode) and `:87` (`startup`, `c->upout=...`).

Evidence: `evidence/request_line_split.pass.log`

### SEC-002 — body_replay_desync: verified upstream-side RCE (high)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw ['POST //x HTTP/1.1', 'GET //exec?cmd=id HTTP/1.1'].

Root cause at `f2b3415b:87` (`startup`, body never framed back).

Evidence: `evidence/body_replay_desync.pass.log`

### SEC-003 — retry_double_exec: verified upstream-side RCE (medium)

Driven by `scripts/probes/rce/row.py` against the tagged release. Observed: control 200, upstream saw status=HTTP/1.1 200 OK executions=2 flaky=['GET ///exec?cmd=id HTTP/1.1'] healthy=['GET ///exec?cmd=id HTTP/1.1'].

Root cause at `f2b3415b:87` (`startup` retry buffer), `FINDING_r13_C.md:49`.

Evidence: `evidence/retry_double_exec.pass.log`

## Artifact index

- `evidence/request_line_split.pass.log` — row.py PASS line for the request_line_split cell
- `evidence/body_replay_desync.pass.log` — row.py PASS line for the body_replay_desync cell
- `evidence/retry_double_exec.pass.log` — row.py PASS line for the retry_double_exec cell
- `evidence/cells.json` — the exact request bytes driven per cell
- `evidence/row_py.log` — the combined 2026-11-18 verification log for this run

## Limitations

- Covers the eight request-smuggling RCE families of the rce_matrix; static-only findings from the earlier audits are recorded in their own envelopes.
