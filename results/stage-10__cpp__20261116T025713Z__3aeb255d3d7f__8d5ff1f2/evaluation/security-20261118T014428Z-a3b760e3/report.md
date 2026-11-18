# Security audit — run 8d5f — release/000002 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The value retains its NUL byte and is re-emitted, so a C-string client loses everything after it. The NUL scan on this build applies to the configuration decoder only, not to relayed header values.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A NUL inside a header value is passed through although the config decoder scans for NULs | line 85 (`trim`) | `evidence/ev_r12_V_8d5f_nul.txt` |

## Findings

### SEC-001 — A NUL inside a header value is passed through although the config decoder scans for NULs

The value retains its NUL byte and is re-emitted, so a C-string client loses everything after it. The NUL scan on this build applies to the configuration decoder only, not to relayed header values.

Evidence: `evidence/ev_r12_V_8d5f_nul.txt`

## Artifact index

- `evidence/ev_r12_V_8d5f_nul.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
