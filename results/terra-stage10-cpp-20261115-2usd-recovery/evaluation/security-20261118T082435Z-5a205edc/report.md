# Security audit — run 2usd — release/000007 (round 11, lane A2)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Precondition matrix cell `pct2f` driven and captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | decoded %2f separator reaches the upstream request line and executes | line 78 (`proxyfetch`) | `evidence/ev_r15_A2_2usd_pct2f.log` |

## Findings

### SEC-001 — decoded %2f separator reaches the upstream request line and executes

Round-15 completion of the RCE-precondition matrix. `pct2f` driven control-first on the final tag, upstream request bytes captured in hex. Execution (where present) is on the upstream host.

Evidence: `evidence/ev_r15_A2_2usd_pct2f.log`

## Artifact index

- `evidence/ev_r15_A2_2usd_pct2f.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
