# Security audit — run 6baf167b — release/000001 (round 10, lane N)

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

Vhost selection works but is then overwritten: `root` is chosen from the Host at this line and immediately reassigned to `aliasroot`, so `Host: beta.test` on an alias path is answered from the alias root. The escape crosses vhost roots too.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | The alias branch overwrites the vhost-selected root after host validation, so a vhost choice is discarded on any alias path | line 81 (`r.host==c->beta?c->betaroot:c->root`) | `evidence/ev_r10_N_6bafv_vhost.bin` |

## Findings

### SEC-001 — The alias branch overwrites the vhost-selected root after host validation, so a vhost choice is discarded on any alias path

`/b.txt` with `Host: beta.test` is 200 `beta` while `Host: alpha.test` is 404, proving the vhost root is live — but on `/al/x.txt` both hosts return MARKER-ALIASDIR-x.txt. S14 shows `/al../alpha/x.txt` from the beta host reading the alpha root, so the escape crosses roots, not just directories.

Evidence: `evidence/ev_r10_N_6bafv_vhost.bin`

## Artifact index

- `evidence/ev_r10_N_6bafv_vhost.bin`

## Limitations

- Filesystem read only.
- Needs a second `server_name`/`host_root`; the vhost itself works (`/b.txt` beta 200, alpha 404).
