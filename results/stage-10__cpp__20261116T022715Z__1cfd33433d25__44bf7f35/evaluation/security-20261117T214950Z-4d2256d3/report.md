# Security audit — run 44bf7f35 — release/000001 (round 10, lane N)

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

0 of 14 shapes escaped. `:74` rejects any alias or location not ending in `/`, so the location is `/al/`; `/al../x.txt` fails `starts_with("/al/")` and 404s at S08, and the written-component form `/al/../x.txt` is 403 at `:82`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Negative: the parser forces alias and location to end in `/`, so `/al..` misses the location and component `..` is refused | line 91 (`path.substr(loc->path.size())`) | `evidence/ev_r10_N_44bfs.ev` |

## Findings

### SEC-001 — Negative: the parser forces alias and location to end in `/`, so `/al..` misses the location and component `..` is refused

The parser forces the trailing slash, which removes exactly the slack the slice needs. S08 404 (prefix miss), S09 403 (component `..` refused), 0/14.

Evidence: `evidence/ev_r10_N_44bfs.ev`

## Artifact index

- `evidence/ev_r10_N_44bfs.ev`

## Limitations

- Filesystem read only.
- Negative on this build only; the slice expression itself is the same as the escaping siblings.
