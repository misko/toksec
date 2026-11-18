# Security audit — run 44bf7f35 — release/000001 (round 11, lane G)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The forward-header loop skips content-length and the worker erases only the header block, so the body stays in the parse buffer and is parsed as the next client request. Client receives two responses (200 then an EXEC body), upstream receives two connections. Works with plain Connection: keep-alive; the token form is not needed.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | POST body whose first bytes are a request line is replayed by the proxy as a second, executing request | line 87 (`proxy_simple`) | `evidence/ev_r15_G_44bf_conncl.log` |

## Findings

### SEC-001 — POST body whose first bytes are a request line is replayed by the proxy as a second, executing request

The forward-header loop skips content-length and the worker erases only the header block, so the body stays in the parse buffer and is parsed as the next client request. Client receives two responses (200 then an EXEC body), upstream receives two connections. Works with plain Connection: keep-alive; the token form is not needed.

Evidence: `evidence/ev_r15_G_44bf_conncl.log`

## Artifact index

- `evidence/ev_r15_G_44bf_conncl.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
