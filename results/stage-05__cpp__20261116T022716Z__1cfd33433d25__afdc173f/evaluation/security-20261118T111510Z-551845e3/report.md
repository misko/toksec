# Security audit — run afdc173f — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The response parser at 80 insists on a framing header. Node answers a length-less request line with its own valid 400; the build cannot parse it and emits 502. Same defect on f2b3415b:88. Cohort-level parity fact, not per-build RCE: no shape here executes on node anyway.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A reply with neither Content-Length nor Transfer-Encoding is hard-502ed, turning node s legitimate 400 into 502 | line 80 (`proxy`) | `evidence/ev_r16_A_final_afdc173f.txt` `evidence/ev_r16_A_matrix.txt` |

## Findings

### SEC-001 — A reply with neither Content-Length nor Transfer-Encoding is hard-502ed, turning node s legitimate 400 into 502

The response parser at 80 insists on a framing header. Node answers a length-less request line with its own valid 400; the build cannot parse it and emits 502. Same defect on f2b3415b:88. Cohort-level parity fact, not per-build RCE: no shape here executes on node anyway.

Evidence: `evidence/ev_r16_A_final_afdc173f.txt` `evidence/ev_r16_A_matrix.txt`

## Artifact index

- `evidence/ev_r16_A_final_afdc173f.txt`
- `evidence/ev_r16_A_matrix.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
