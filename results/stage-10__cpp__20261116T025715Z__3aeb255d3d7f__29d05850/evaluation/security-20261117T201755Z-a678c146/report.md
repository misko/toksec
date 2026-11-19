# Security audit — run 29d05850 — release/000002 (round 9, lane L)

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
| SEC-001 | yes | informational | line 50 (`hdr.count("expect")`) | line 50 (`hdr.count("expect")`) | `evidence/ev_r9_L_29d05850_expect_bodyloss.ev` |
| SEC-002 | no | informational | line 50 (`istringstream ss(lines[0])`) | line 50 (`istringstream ss(lines[0])`) | `evidence/ev_r9_L_29d05850_expect_tokenizer_host.ev` |
| SEC-003 | no | informational | line 50 (`hostname(host)`) | line 50 (`hostname(host)`) | `evidence/ev_r9_L_29d05850_hostport.ev` |

## Findings

### SEC-001 — line 50 (`hdr.count("expect")`)

`hdr.count("expect")` at line 50. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_29d05850_expect_bodyloss.ev`

### SEC-002 — line 50 (`istringstream ss(lines[0])`)

`istringstream ss(lines[0])` at line 50. Verdict: negative, counted.

Evidence: `evidence/ev_r9_L_29d05850_expect_tokenizer_host.ev`

### SEC-003 — line 50 (`hostname(host)`)

`hostname(host)` at line 50. Verdict: negative, counted.

Evidence: `evidence/ev_r9_L_29d05850_hostport.ev`

## Artifact index

- `evidence/ev_r9_L_29d05850_expect_bodyloss.ev`
- `evidence/ev_r9_L_29d05850_expect_tokenizer_host.ev`
- `evidence/ev_r9_L_29d05850_hostport.ev`

## Limitations

- Upstream-host execution only.
- The `Expect` 417 is a correctness/availability defect, not code execution.
