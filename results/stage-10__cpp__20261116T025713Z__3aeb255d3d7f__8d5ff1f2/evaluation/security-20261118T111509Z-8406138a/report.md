# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane A)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The guard at 77 rejects only NUL and backslash, so a decoded 0x09 reaches the upstream request line. Against stock nginx the request line degrades to HTTP/0.9: /exec runs and the caller gets 502. Control (GET /api/exec?cmd=id) is 200 with uid on the same config. Node 400s every exec09 shape.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The only shape that executes on stock software is the encoded-query form, and it executes from a path byte the decoder passes through | line 77 (`pathnorm`) | `evidence/ev_r16_A_cap_8d5ff1f2_exec09crlf.log` `evidence/ev_r16_A_final_8d5ff1f2.txt` |

## Findings

### SEC-001 — The only shape that executes on stock software is the encoded-query form, and it executes from a path byte the decoder passes through

The guard at 77 rejects only NUL and backslash, so a decoded 0x09 reaches the upstream request line. Against stock nginx the request line degrades to HTTP/0.9: /exec runs and the caller gets 502. Control (GET /api/exec?cmd=id) is 200 with uid on the same config. Node 400s every exec09 shape.

Evidence: `evidence/ev_r16_A_cap_8d5ff1f2_exec09crlf.log` `evidence/ev_r16_A_final_8d5ff1f2.txt`

## Artifact index

- `evidence/ev_r16_A_cap_8d5ff1f2_exec09crlf.log`
- `evidence/ev_r16_A_final_8d5ff1f2.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
