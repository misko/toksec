# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

TLS front brings no new defect and costs nothing: the poison still installs and still reaches victims.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | The three-hop TLS headline delivers EXEC to a victim | line 90 (`storecache`) | `evidence/ev_r15_E_tls_headline_victim_client_stream.hex` |

## Findings

### SEC-001 — The three-hop TLS headline delivers EXEC to a victim

TLS front brings no new defect and costs nothing: the poison still installs and still reaches victims.

Evidence: `evidence/ev_r15_E_tls_headline_victim_client_stream.hex`

## Artifact index

- `evidence/ev_r15_E_tls_headline_victim_client_stream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
