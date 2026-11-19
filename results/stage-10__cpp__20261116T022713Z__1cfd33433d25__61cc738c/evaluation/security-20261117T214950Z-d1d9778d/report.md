# Security audit — run 61cc738c — release/000001 (round 10, lane N)

The alias length as an unmeasured slice. Release source read from the tag, byte-identical to the
staged copy.

Filesystem read only — the proxy serves bytes; all RCE in this corpus remains RCE on the
**upstream host**.

## Audit narrative

`rel = decoded_path.substr(<alias length>)` runs after a prefix compare and never compares the
decoded path's length against the alias first. Doc root `/tmp/r10_www_N` holds distinct one-line
markers per file, so the file actually opened is unambiguous. Controls: plain alias hit
(`aliasdir/x.txt`) and root hit (`alpha/x.txt`), both 200 on the same cold server, before any
payload. Alias is `/al` (length 3); `/al../x.txt` decodes to 10 chars, so `substr(3)` produces
the 8-char `../x.txt` — a `..` **produced by the slice**, not one the client wrote as a component.

0 of 14. `:50` refuses a location or alias not ending in `/`, giving the same 404 at S08 and 403 at S09.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Negative: same trailing-slash forcing (`bad alias`), so the slice escape is unavailable | line 66 (`path.substr(l.path.size())`) | `evidence/ev_r10_N_61ccs.ev` |

## Findings

### SEC-001 — Negative: same trailing-slash forcing (`bad alias`), so the slice escape is unavailable

Identical mechanism to 44bf7f35: the forced trailing slash means `/al..` never prefix-matches, and a written component `..` is refused. S08 404, S09 403, 0/14.

Evidence: `evidence/ev_r10_N_61ccs.ev`

## Artifact index

- `evidence/ev_r10_N_61ccs.ev`

## Limitations

- Filesystem read only.
- Negative on this build only.
