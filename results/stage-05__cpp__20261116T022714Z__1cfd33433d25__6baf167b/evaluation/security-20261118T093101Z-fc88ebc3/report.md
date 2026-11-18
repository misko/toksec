# Security audit — run 6baf167b — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Negative from source grep.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | No SSL path exists at all on this build, so it cannot be a TLS head end | line 110 (`main`) | `evidence/ev_r15_E_queryonly_6b_upstream.hex` |

## Findings

### SEC-001 — No SSL path exists at all on this build, so it cannot be a TLS head end

Negative from source grep.

Evidence: `evidence/ev_r15_E_queryonly_6b_upstream.hex`

## Artifact index

- `evidence/ev_r15_E_queryonly_6b_upstream.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
