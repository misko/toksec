# Security audit — run f2b3415b — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(400, reference 200+200) Same shape; `pipe_ctl` control gives 200 + 200 (`ev_r14_A_f2b3415b_v2_out.log`), `pipe_crlf` gives
400 with zero upstream requests. Same rejection reason as §11 in its own decoder.
Source line: **line 49 (`pathdecode`)** — `if(c==0||c=='\\'||c<32||c==127)return false;`.
Precondition: same as §11. Evidence: `ev_r14_A_f2b3415b_v2_out.log`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `pipe_crlf` — f2b3415b pathdecode | line 49 (`pathdecode`) | `evidence/ev_r14_A_f2b3415b_v2_out.log` |

## Findings

### SEC-001 — negative for `pipe_crlf` — f2b3415b pathdecode

(400, reference 200+200) Same shape; `pipe_ctl` control gives 200 + 200 (`ev_r14_A_f2b3415b_v2_out.log`), `pipe_crlf` gives
400 with zero upstream requests. Same rejection reason as §11 in its own decoder.
Source line: **line 49 (`pathdecode`)** — `if(c==0||c=='\\'||c<32||c==127)return false;`.
Precondition: same as §11. Evidence: `ev_r14_A_f2b3415b_v2_out.log`.

Evidence: `evidence/ev_r14_A_f2b3415b_v2_out.log`

## Artifact index

- `evidence/ev_r14_A_f2b3415b_v2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
