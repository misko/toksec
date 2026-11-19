# Security audit — run 2usd — release/000007 (round 11, lane A2)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Precondition matrix cell `multi` driven and captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | separator payload yields a 4-token upstream line (RCE precondition met) | line 78 (`proxyfetch`) | `evidence/ev_r15_A2_2usd_multi.log` |

## Findings

### SEC-001 — separator payload yields a 4-token upstream line (RCE precondition met)

Round-15 completion of the RCE-precondition matrix. `multi` driven control-first on the final tag, upstream request bytes captured in hex. Execution (where present) is on the upstream host.

Evidence: `evidence/ev_r15_A2_2usd_multi.log`

## Artifact index

- `evidence/ev_r15_A2_2usd_multi.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
