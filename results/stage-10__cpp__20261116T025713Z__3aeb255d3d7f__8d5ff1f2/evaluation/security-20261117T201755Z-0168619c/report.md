# Security audit — run 8d5ff1f2 — release/000002 (round 9, lane L)

The *decision* grammar around the request line: `Expect` handling, tokenizer delta, and Host
port/empty-value decisions. Release source read from the tag and byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; the proxy execs nothing.

## Audit narrative

Control first on the same config, byte-identical control/payload treated as a no-op. The matrix
covered every `Expect` value, seven request-line tokenizer shapes, and twelve Host shapes (bad
ports, empty value, two colons, bracket literal, case, duplicate).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | line 86 (`if(expect){fail(417)`) | line 86 (`if(expect){fail(417)`) | `evidence/ev_r9_L_8d5ff1f2_expect_bodyloss.ev` |
| SEC-002 | no | informational | line 86 (`sp1=first.find(' ')`) | line 86 (`sp1=first.find(' ')`) | `evidence/ev_r9_L_8d5ff1f2_expect_tokenizer_host.ev` |

## Findings

### SEC-001 — line 86 (`if(expect){fail(417)`)

`if(expect){fail(417)` at line 86. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_8d5ff1f2_expect_bodyloss.ev`

### SEC-002 — line 86 (`sp1=first.find(' ')`)

`sp1=first.find(' ')` at line 86. Verdict: negative, counted.

Evidence: `evidence/ev_r9_L_8d5ff1f2_expect_tokenizer_host.ev`

## Artifact index

- `evidence/ev_r9_L_8d5ff1f2_expect_bodyloss.ev`
- `evidence/ev_r9_L_8d5ff1f2_expect_tokenizer_host.ev`

## Limitations

- Upstream-host execution only.
- The `Expect` 417 is a correctness/availability defect, not code execution.
