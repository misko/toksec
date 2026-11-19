# Security audit — run 8d5f — release/000002 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The upstream emits one header line containing a bare LF. The proxy accepts it, so the second half becomes a real header, and re-emits both with CRLF. Clients that also split on bare LF see one extra field compared with the pass-raw builds that hand the LF through unchanged.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A bare-LF header split is parsed and then re-authored with CRLF, giving LF-lenient and CRLF-strict clients different field sets | line 85 (`fields+=k`) | `evidence/ev_r12_V_8d5f_bareLF.txt` `evidence/ev_r12_V_8d5f_nul.txt` |

## Findings

### SEC-001 — A bare-LF header split is parsed and then re-authored with CRLF, giving LF-lenient and CRLF-strict clients different field sets

The upstream emits one header line containing a bare LF. The proxy accepts it, so the second half becomes a real header, and re-emits both with CRLF. Clients that also split on bare LF see one extra field compared with the pass-raw builds that hand the LF through unchanged.

Evidence: `evidence/ev_r12_V_8d5f_bareLF.txt` `evidence/ev_r12_V_8d5f_nul.txt`

## Artifact index

- `evidence/ev_r12_V_8d5f_bareLF.txt`
- `evidence/ev_r12_V_8d5f_nul.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
