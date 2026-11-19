# Security audit — run 8d5ff1f2 — release/000002 (round 9, lane J)

Static byte-range arithmetic as an integer sink. Release source read from the tag and
byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; these builds are static-only.

## Audit narrative

Fixture set A (1 byte), B (10 bytes), C (4 KiB), D (empty), E (11 bytes), plus 64 MiB boundary
files. Control first on every config. 330 range shapes per build across the four audited builds:
suffix, open-ended, inverted, over-size, leading zeros, whitespace, duplicate dash, 64-bit
overflow, and HEAD-versus-GET pairs, each measured for received bytes rather than trusting the
header.

**The lane question, answered.** The trusted length is the *parsed end*, and the emitted
Content-Length is computed from that same variable, so the two cannot diverge: zero
Content-Length-versus-received mismatches on all four builds. The real divergence is a cap gate
evaluated on the wrong quantity.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Range arithmetic is exact on every driven shape; the only anomaly is the shared bogus reason phrase on a 206 | line 91 (`digits=[](string z)`) | `evidence/ev_r9_J_num_3aeb255d3d7f__8d5ff1f2.log` |

## Findings

### SEC-001 — Range arithmetic is exact on every driven shape; the only anomaly is the shared bogus reason phrase on a 206

330 shapes with zero Content-Length versus received-byte mismatches, zero Content-Range span versus CL mismatches, zero out-of-file spans and zero HEAD-versus-GET disagreements. The digits parser is a local lambda with an explicit overflow bound and the trusted length is the same variable the header is built from. The single oddity is the cosmetic 206 Error status line from the shared reason table. Recorded as the clean contrast build.

Evidence: `evidence/ev_r9_J_num_3aeb255d3d7f__8d5ff1f2.log`

## Artifact index

- `evidence/ev_r9_J_num_3aeb255d3d7f__8d5ff1f2.log`

## Limitations

- Static builds; nothing executes.
- The cap findings need a file at or over 64 MiB.
- Sparse multi-GiB files were tested by offset only, not by full transfer.
