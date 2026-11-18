# Security audit — run 44bf7f35 — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(POST body replayed as a second request) Class: framing desync / request smuggling, client-visible double response.
Control first: `ctl` -> 200 `BODY-0123456789`, one upstream `GET /api/hello.txt`
(`ev_r14_A_44bf7f35_v2_out.log`).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | smuggle — 44bf7f35 proxy_simple | line 87 (`proxy_simple`) | `evidence/ev_r14_A_44bf7f35_v2.log` `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_replay_44bf.log` `evidence/ev_r14_A_replay_44bf_out.log` |

## Findings

### SEC-001 — smuggle — 44bf7f35 proxy_simple

(POST body replayed as a second request) Class: framing desync / request smuggling, client-visible double response.
Control first: `ctl` -> 200 `BODY-0123456789`, one upstream `GET /api/hello.txt`
(`ev_r14_A_44bf7f35_v2_out.log`).

Evidence: `evidence/ev_r14_A_44bf7f35_v2.log` `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_replay_44bf.log` `evidence/ev_r14_A_replay_44bf_out.log`

## Artifact index

- `evidence/ev_r14_A_44bf7f35_v2.log`
- `evidence/ev_r14_A_44bf7f35_v2_out.log`
- `evidence/ev_r14_A_replay_44bf.log`
- `evidence/ev_r14_A_replay_44bf_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
