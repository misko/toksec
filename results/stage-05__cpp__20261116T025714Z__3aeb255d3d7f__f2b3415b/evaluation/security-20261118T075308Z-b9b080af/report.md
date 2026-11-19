# Security audit — run f2b3415b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(`Expect` 400 at the header deadline)

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | transfer — f2b3415b header_to | line 101 (`header_to`) | `evidence/ev_r14_A_expect_f2b_cold.log` `evidence/ev_r14_A_f2b3415b_v2_out.log` |

## Findings

### SEC-001 — transfer — f2b3415b header_to

(`Expect` 400 at the header deadline)

Evidence: `evidence/ev_r14_A_expect_f2b_cold.log` `evidence/ev_r14_A_f2b3415b_v2_out.log`

## Artifact index

- `evidence/ev_r14_A_expect_f2b_cold.log`
- `evidence/ev_r14_A_f2b3415b_v2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
