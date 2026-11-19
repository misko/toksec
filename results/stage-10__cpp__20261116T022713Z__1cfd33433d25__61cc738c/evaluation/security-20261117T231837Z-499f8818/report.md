# Security audit — run 61cc738c — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Byte-identical to 44bf7f35 on all seven shapes: 417 with `Content-Length: 0` and `Connection: close`, `eof` at 0.000 s, body dead, upstream never contacted; a waiting client gets `Broken pipe` on its body write. `break` leaves the keep-alive loop, so there is no leftover-body desync on either R1 build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Same bare 417 with an immediate close; `count()` is presence-only so a duplicate `Expect` is counted but never compared | line 68 (`count(r,"expect")`) | `evidence/ev_r11_R_61cc_p417.txt` |

## Findings

### SEC-001 — Same bare 417 with an immediate close; `count()` is presence-only so a duplicate `Expect` is counted but never compared

Byte-identical to 44bf7f35 on all seven shapes: 417 with `Content-Length: 0` and `Connection: close`, `eof` at 0.000 s, body dead, upstream never contacted; a waiting client gets `Broken pipe` on its body write. `break` leaves the keep-alive loop, so there is no leftover-body desync on either R1 build.

Evidence: `evidence/ev_r11_R_61cc_p417.txt`

## Artifact index

- `evidence/ev_r11_R_61cc_p417.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
