# Security audit — run 6fb186ed — release/000004 (round 9, lane J)

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
| SEC-001 | yes | low | The 64 MiB body cap is checked after the HEAD early return, so HEAD reports 200 for a file whose GET is 403 | line 72 (`length>64*1024*1024`) | `evidence/ev_r9_J_capboundary_6fb186ed.log` |
| SEC-002 | yes | low | An explicit Content-Length range of exactly the cap bypasses the cap gate and serves a file that a plain GET refuses | line 72 (`length>64*1024*1024`) | `evidence/ev_r9_J_cap403_6fb186ed.log` |
| SEC-003 | yes | informational | A 403 from the cap closes mid-pipeline and eats the following request | line 72 (`length>64*1024*1024`) | `evidence/ev_r9_J_pipe_403_6fb186ed.log` |

## Findings

### SEC-001 — The 64 MiB body cap is checked after the HEAD early return, so HEAD reports 200 for a file whose GET is 403

The cap check is on the GET path only; a HEAD request returns before it. A 67108865-byte file answers HEAD with 200 and a Content-Length it can never deliver, while GET is 403: a client that preflights with HEAD, or any link checker or monitoring probe that uses HEAD, sees a healthy resource that cannot actually be fetched. Precondition: a file one byte over the 64 MiB cap.

Evidence: `evidence/ev_r9_J_capboundary_6fb186ed.log`

### SEC-002 — An explicit Content-Length range of exactly the cap bypasses the cap gate and serves a file that a plain GET refuses

The cap compares the computed body length, not the file size, so Range: bytes=0-67108863 on a 67108865-byte file computes exactly the cap, passes the gate, and returns 206 with the first 64 MiB. The same file with no Range, or with bytes=0-67108864, is 403. Precondition: a file over the cap and an attacker-chosen Range.

Evidence: `evidence/ev_r9_J_cap403_6fb186ed.log`

### SEC-003 — A 403 from the cap closes mid-pipeline and eats the following request

The 403 is emitted with Connection: close, so a pipelined successor behind the oversized-file request is dropped exactly as with any other closing response. Recorded for composition, not as a new defect. Precondition: pipelining plus an over-cap file.

Evidence: `evidence/ev_r9_J_pipe_403_6fb186ed.log`

## Artifact index

- `evidence/ev_r9_J_capboundary_6fb186ed.log`
- `evidence/ev_r9_J_cap403_6fb186ed.log`
- `evidence/ev_r9_J_pipe_403_6fb186ed.log`

## Limitations

- Static builds; nothing executes.
- The cap findings need a file at or over 64 MiB.
- Sparse multi-GiB files were tested by offset only, not by full transfer.
