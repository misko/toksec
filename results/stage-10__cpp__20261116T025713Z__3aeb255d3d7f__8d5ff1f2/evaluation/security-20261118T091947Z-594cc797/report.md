# Security audit — run 8d5ff1f2 — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

getline on LF over an already-terminated block: the value is cut and the remainder is parsed as a new header and re-emitted. 11 header bytes in become 12 out with a minted header - a split, not a rewrite and not hop-by-hop stripping.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Bare LF in an upstream header value splits the line and mints a client header the peer never sent | line 85 (`proxy_request`) | `evidence/ev_r15_F_cli_3aeb255d3d7f__8d5ff1f2_lfcol.txt` `evidence/ev_r15_F_8d5full.json` |

## Findings

### SEC-001 — Bare LF in an upstream header value splits the line and mints a client header the peer never sent

getline on LF over an already-terminated block: the value is cut and the remainder is parsed as a new header and re-emitted. 11 header bytes in become 12 out with a minted header - a split, not a rewrite and not hop-by-hop stripping.

Evidence: `evidence/ev_r15_F_cli_3aeb255d3d7f__8d5ff1f2_lfcol.txt` `evidence/ev_r15_F_8d5full.json`

## Artifact index

- `evidence/ev_r15_F_cli_3aeb255d3d7f__8d5ff1f2_lfcol.txt`
- `evidence/ev_r15_F_8d5full.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
