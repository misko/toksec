# Security audit — run 2usd — release/000007 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

proxyfetch reads the already-cut block with while(getline(ss,line)), so a bare LF ends the line; the X-P: prefix is re-emitted with an empty remainder and the orphan tail is dropped by the col==npos guard. CR and DEL are carried raw.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value is verbatim except a bare LF, which empties the value and drops the tail | line 78 (`proxyfetch`) | `evidence/ev_r15_F_build_r12_W_2usd.txt` |

## Findings

### SEC-001 — Upstream response-header value is verbatim except a bare LF, which empties the value and drops the tail

proxyfetch reads the already-cut block with while(getline(ss,line)), so a bare LF ends the line; the X-P: prefix is re-emitted with an empty remainder and the orphan tail is dropped by the col==npos guard. CR and DEL are carried raw.

Evidence: `evidence/ev_r15_F_build_r12_W_2usd.txt`

## Artifact index

- `evidence/ev_r15_F_build_r12_W_2usd.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
