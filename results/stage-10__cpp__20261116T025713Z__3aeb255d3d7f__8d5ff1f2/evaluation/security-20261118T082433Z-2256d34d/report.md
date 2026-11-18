# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane A2)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Precondition matrix cell `expect` driven and captured.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Expect gate precedes the proxy — Connection: expect cannot rescue it | line 86 (`expect`) | `evidence/ev_r15_A2_8d5ff1f2_expect.log` |

## Findings

### SEC-001 — Expect gate precedes the proxy — Connection: expect cannot rescue it

Round-15 completion of the RCE-precondition matrix. `expect` driven control-first on the final tag, upstream request bytes captured in hex. Execution (where present) is on the upstream host.

Evidence: `evidence/ev_r15_A2_8d5ff1f2_expect.log`

## Artifact index

- `evidence/ev_r15_A2_8d5ff1f2_expect.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
