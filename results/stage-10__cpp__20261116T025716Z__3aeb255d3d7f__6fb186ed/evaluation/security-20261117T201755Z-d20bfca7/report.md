# Security audit — run 6fb186ed — release/000004 (round 9, lane L)

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
| SEC-001 | yes | low | line 64 (`first.find(' ')`) | line 64 (`first.find(' ')`) | `evidence/ev_r9_L_6fb_tab_exec_delta.ev` |
| SEC-002 | yes | low | line 68 (`string uri=target;`) | line 68 (`string uri=target;`) | `evidence/ev_r9_L_6fb_tab_rewrite_loc.ev` |
| SEC-003 | yes | informational | line 65 (`host.resize(host.find(':'))`) | line 65 (`host.resize(host.find(':'))`) | `evidence/ev_r9_L_6fb186ed_hostport.ev` |
| SEC-004 | yes | informational | line 65 (`host.resize(host.find(':'))`) | line 65 (`host.resize(host.find(':'))`) | `evidence/ev_r9_L_6fb_emptyhost_shared.ev` |
| SEC-005 | yes | informational | line 65 (`headers.count("expect")`) | line 65 (`headers.count("expect")`) | `evidence/ev_r9_L_6fb186ed_expect_tokenizer_host.ev` |

## Findings

### SEC-001 — line 64 (`first.find(' ')`)

`first.find(' ')` at line 64. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_6fb_tab_exec_delta.ev`

### SEC-002 — line 68 (`string uri=target;`)

`string uri=target;` at line 68. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_6fb_tab_rewrite_loc.ev`

### SEC-003 — line 65 (`host.resize(host.find(':'))`)

`host.resize(host.find(':'))` at line 65. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_6fb186ed_hostport.ev`

### SEC-004 — line 65 (`host.resize(host.find(':'))`)

`host.resize(host.find(':'))` at line 65. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_6fb_emptyhost_shared.ev`

### SEC-005 — line 65 (`headers.count("expect")`)

`headers.count("expect")` at line 65. Verdict: remote effect.

Evidence: `evidence/ev_r9_L_6fb186ed_expect_tokenizer_host.ev`

## Artifact index

- `evidence/ev_r9_L_6fb_tab_exec_delta.ev`
- `evidence/ev_r9_L_6fb_tab_rewrite_loc.ev`
- `evidence/ev_r9_L_6fb186ed_hostport.ev`
- `evidence/ev_r9_L_6fb_emptyhost_shared.ev`
- `evidence/ev_r9_L_6fb186ed_expect_tokenizer_host.ev`

## Limitations

- Upstream-host execution only.
- The `Expect` 417 is a correctness/availability defect, not code execution.
