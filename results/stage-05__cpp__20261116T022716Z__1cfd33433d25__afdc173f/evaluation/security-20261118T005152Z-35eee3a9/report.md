# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Attempt 1 and attempt 2 are byte-identical apart from the Host authority: no second prefix strip, no re-decode, and the Connection-nominated deletion applies identically on both attempts. Recorded as the negative that makes the double-execute claim safe.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Retry re-serializes the already-decoded path and slices the prefix exactly once | line 80 (`q.path.substr`) | `evidence/ev_r12_X_ev_afdc_close.txt` `evidence/ev_r12_X_ev_afdc_dblprefix.txt` `evidence/ev_r12_X_ev_afdc_hdrstrip.txt` |

## Findings

### SEC-001 — Retry re-serializes the already-decoded path and slices the prefix exactly once

Attempt 1 and attempt 2 are byte-identical apart from the Host authority: no second prefix strip, no re-decode, and the Connection-nominated deletion applies identically on both attempts. Recorded as the negative that makes the double-execute claim safe.

Evidence: `evidence/ev_r12_X_ev_afdc_close.txt` `evidence/ev_r12_X_ev_afdc_dblprefix.txt` `evidence/ev_r12_X_ev_afdc_hdrstrip.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_close.txt`
- `evidence/ev_r12_X_ev_afdc_dblprefix.txt`
- `evidence/ev_r12_X_ev_afdc_hdrstrip.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
