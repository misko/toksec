# Security audit — run f2b3415b — release/000001 (round 10, lane N)

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

0 of 14. The slice is correct (`../x.txt`) but `openpath` at `:75` refuses any component equal to `..` (`if(p==".."){close(fd);return -403;}`), so S08/S09/S10 are all 403.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Negative: the slice does produce `../x.txt` but `openpath` rejects the `..` component | line 78 (`r.path.substr(cfg.alias.size())`) | `evidence/ev_r10_N_f2bs.ev` |

## Findings

### SEC-001 — Negative: the slice does produce `../x.txt` but `openpath` rejects the `..` component

The only build where the slice is computed correctly and then discarded by the component guard. Shows the defect is the *walk*, not the subtraction, and that the two are independent.

Evidence: `evidence/ev_r10_N_f2bs.ev`

## Artifact index

- `evidence/ev_r10_N_f2bs.ev`

## Limitations

- Filesystem read only.
- Negative on this build only, and the sharpest contrast: the arithmetic is right, the walk is what refuses.
