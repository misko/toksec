# Security audit — run 063b0d5e — release/000002 (round 10, lane N)

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

Every build rejects the written component: 400 or 403 across all eleven. So `..` alone was already dead, and the primitive is specifically the `..` the slice manufactures.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Boundary: a written component `..` (`/al/..%2fx.txt`) is refused on all eleven builds — only a slice-produced `..` escapes | line 47 (`if(seg=="..")return false`) | `evidence/ev_r10_N_063b_esc.bin` |

## Findings

### SEC-001 — Boundary: a written component `..` (`/al/..%2fx.txt`) is refused on all eleven builds — only a slice-produced `..` escapes

`/al/..%2fx.txt` decodes to `/al/../x.txt`, whose `..` is a real component. All eleven builds refuse it (400 at this line's `if(seg=="..")return false`, 403 on the rest), which is why the lane's escape is new rather than a re-discovery of the known `..` 403.

Evidence: `evidence/ev_r10_N_063b_esc.bin`

## Artifact index

- `evidence/ev_r10_N_063b_esc.bin`

## Limitations

- Filesystem read only.
- Six other builds guard in the `split` loop with the same `s==".."` test; counted rather than each cited.
