# Security audit — run 29d05850 — release/000002 (round 10, lane N)

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

Escape confirmed on the normalized string: the build routes on `norm` then slices it, so the arithmetic is identical and the produced `..` still escapes.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The normalized-path variant slices `norm`, so the same produced `..` escapes | line 50 (`norm.substr(l->path.size())`) | `evidence/ev_r10_N_29ds.ev` |

## Findings

### SEC-001 — The normalized-path variant slices `norm`, so the same produced `..` escapes

`GET /al../x.txt` with alias `/al:/tmp/r10_www_N/aliasdir`. Decoded `/al../x.txt` is 10 chars, the alias is 3, `substr(3)` yields `../x.txt`; `openat` walks `aliasdir`, then `..` per the open loop's component walk and opens `/tmp/r10_www_N/x.txt` = **MARKER-PARENT-ESCAPE** (200), one level above the alias root. The plain `/al/x.txt` control returns MARKER-ALIASDIR-x.txt and `/x.txt` returns MARKER-alpha-x.txt on the same cold server, so the marker is not a default.

Evidence: `evidence/ev_r10_N_29ds.ev`

## Artifact index

- `evidence/ev_r10_N_29ds.ev`

## Limitations

- Filesystem read only.
- Different shape: routes on the normalized string and slices that, not the raw decoded path.
