# Security audit — run 61cc738c — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(417, reference sends 100) Same shape and control (`ev_r14_A_61cc738c_v2_out.log`), identical client bytes to §3.
Source line: **line 68 (`serve`)** — `if(count(r,"expect")){sendhead(io,417,0,true);break;}`.
Precondition: same as §3. Evidence: `ev_r14_A_61cc738c_v2_out.log`. Known family.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `Expect` — 61cc738c serve | line 68 (`serve`) | `evidence/ev_r14_A_61cc738c_v2_out.log` |

## Findings

### SEC-001 — negative for `Expect` — 61cc738c serve

(417, reference sends 100) Same shape and control (`ev_r14_A_61cc738c_v2_out.log`), identical client bytes to §3.
Source line: **line 68 (`serve`)** — `if(count(r,"expect")){sendhead(io,417,0,true);break;}`.
Precondition: same as §3. Evidence: `ev_r14_A_61cc738c_v2_out.log`. Known family.

Evidence: `evidence/ev_r14_A_61cc738c_v2_out.log`

## Artifact index

- `evidence/ev_r14_A_61cc738c_v2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
