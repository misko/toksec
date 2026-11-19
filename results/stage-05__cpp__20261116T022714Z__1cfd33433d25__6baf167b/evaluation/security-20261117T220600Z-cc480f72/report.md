# Security audit — run 6baf167b — release/000001 (round 10, lane O)

`..` in prefix position, cited at the guard itself. Release source read from the tag, byte-identical
to the staged copy.

All RCE in this corpus is RCE on the **upstream host**.

## Audit narrative

Control first, then one hex-exact request. The sink is the upstream request line; `..` is guarded
only in the static branch, so a proxied `..` travels verbatim.

`6baf167b` guards `..` only inside `local()`; dispatch at `:109` takes the proxy branch first, so the guard never runs on a proxied request. This is the one build of seventeen where the guard is on the wrong branch, and the string it lets through is a live `..`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | no | low | The `..` guard runs only in the static branch, so a proxied `..` reaches the upstream request line and escapes a level | line 80 (`local`) | `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex` |

## Findings

### SEC-001 — The `..` guard runs only in the static branch, so a proxied `..` reaches the upstream request line and escapes a level

`/api/../exec?cmd=id` decodes to path `/api/../exec`; the rewrite emits `"/"+path.substr(4)` = `/../exec`, so the peer receives `GET //../exec?cmd=id`. The proxy has removed the `/api` prefix the client typed and handed the `..` to the upstream untouched. Proven twice: the exact-token peer echoes `RAW=b'GET //../exec?cmd=id HTTP/1.1'` with `TOKS=3 EXEC=1`, and an independent naive concatenating upstream (no normalisation, opens ROOT+token[1]) returns `EXEC-ONE-LEVEL-UP` from `/tmp/.../up//../exec` instead of `EXEC-AT-UPDOCROOT` from the control's `/tmp/.../up//exec` — a different file. 3/3 from cold on both upstreams; `%2e%2e` behaves identically.

Evidence: `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex`

## Artifact index

- `evidence/ev_r10_O_1cfd33433d25_6baf167b_P2.hex`

## Limitations

- Upstream-host execution only.
- Needs a proxied prefix location and an upstream that resolves `..`.
