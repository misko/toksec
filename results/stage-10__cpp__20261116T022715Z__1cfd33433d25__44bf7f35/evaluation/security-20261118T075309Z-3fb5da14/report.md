# Security audit — run 44bf7f35 — release/000001 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

(400, reference 200+200) Same shape; `pipe_ctl` control gives 200 + 200 (`ev_r14_A_44bf7f35_v2_out.log`), `pipe_crlf` gives
400 with zero upstream requests.
Source line: **line 82 (`normpath`)** — `if(c==0||c=='\\'||c<32||c==127)return 400;`.
Precondition: same as §11. Evidence: `ev_r14_A_44bf7f35_v2_out.log`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | negative for `pipe_crlf` — 44bf7f35 normpath | line 82 (`normpath`) | `evidence/ev_r14_A_44bf7f35_v2_out.log` |

## Findings

### SEC-001 — negative for `pipe_crlf` — 44bf7f35 normpath

(400, reference 200+200) Same shape; `pipe_ctl` control gives 200 + 200 (`ev_r14_A_44bf7f35_v2_out.log`), `pipe_crlf` gives
400 with zero upstream requests.
Source line: **line 82 (`normpath`)** — `if(c==0||c=='\\'||c<32||c==127)return 400;`.
Precondition: same as §11. Evidence: `ev_r14_A_44bf7f35_v2_out.log`.

Evidence: `evidence/ev_r14_A_44bf7f35_v2_out.log`

## Artifact index

- `evidence/ev_r14_A_44bf7f35_v2_out.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
