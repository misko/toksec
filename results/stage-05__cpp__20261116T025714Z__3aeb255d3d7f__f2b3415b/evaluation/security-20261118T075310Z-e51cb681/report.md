# Security audit — run f2b3415b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(chunked + trailing byte -> 502) ## Negatives worth recording

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | transfer — f2b3415b used!=s.size() | line 89 (`used!=s.size()`) | `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_6baf167b_v2.log` |

## Findings

### SEC-001 — transfer — f2b3415b used!=s.size()

(chunked + trailing byte -> 502) ## Negatives worth recording

Evidence: `evidence/ev_r14_A_44bf7f35_v2_out.log` `evidence/ev_r14_A_61cc738c_v2.log` `evidence/ev_r14_A_61cc738c_v2_out.log` `evidence/ev_r14_A_6baf167b_v2.log`

## Artifact index

- `evidence/ev_r14_A_44bf7f35_v2_out.log`
- `evidence/ev_r14_A_61cc738c_v2.log`
- `evidence/ev_r14_A_61cc738c_v2_out.log`
- `evidence/ev_r14_A_6baf167b_v2.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
