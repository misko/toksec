# Security audit — run 44bf7f35 — release/000001 (round 11, lane A2)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Precondition matrix cell `multi` driven and captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | separator payload yields a 4-token upstream line (RCE precondition met) | line 87 (`proxy_simple`) | `evidence/ev_r15_A2_44bf7f35_multi.log` |

## Findings

### SEC-001 — separator payload yields a 4-token upstream line (RCE precondition met)

Round-15 completion of the RCE-precondition matrix. `multi` driven control-first on the final tag, upstream request bytes captured in hex. Execution (where present) is on the upstream host.

Evidence: `evidence/ev_r15_A2_44bf7f35_multi.log`

## Artifact index

- `evidence/ev_r15_A2_44bf7f35_multi.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
