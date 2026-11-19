# Security audit — run 063b0d5e — release/000002 (round 10, lane P)

Composing round-8/9 defects on one connection, control first. Release source read from the tag,
byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request line.

## Audit narrative

The attacker string does not widen; what changes is *which request the attacker's bytes are framed
against and which client's response they are counted in*. The length measured once and then trusted
is the upstream's own declared `Content-Length`: it is copied into the client head and never
reconciled with the bytes relayed, so a short upstream body is stamped with a long CL and the
deficit is filled from the next response. Peer lines carry a `SEQ:` counter and a token count, so a
follower reaching upstream as its own request is proven, not asserted.

The 100 is consumed correctly here (no extra head, 2 requests -> 2 heads), but the interim length survives into the real head: `Content-Length: 400` with 100 bytes, then the follower response, connection left open. So it contributes a wrong length rather than a wrong frame.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | The interim Content-Length becomes `respleft` and the terminal head inherits it, giving the client a wrong body length under a live connection | line 69 (`to_string(len)`) | `evidence/ev_r10_P_poc_063b0d5e.hex` `evidence/ev_r10_P_client_063b0d5e.txt` |

## Findings

### SEC-001 — The interim Content-Length becomes `respleft` and the terminal head inherits it, giving the client a wrong body length under a live connection

`GET /api%2fexec%20?cmd=id&mode=sub%20n=60` pipelined with a follower: the client's `CL:19` window ends exactly on the exec body (no shift), while the overlong variant reproduces the 29d short-body shape. Any non-zero request `Content-Length` is a 400 at `:53`, so a body-framed follower is impossible on this build.

Evidence: `evidence/ev_r10_P_poc_063b0d5e.hex` `evidence/ev_r10_P_client_063b0d5e.txt`

## Artifact index

- `evidence/ev_r10_P_poc_063b0d5e.hex`
- `evidence/ev_r10_P_client_063b0d5e.txt`

## Limitations

- Intra-connection only; no cross-client leak found.
- Needs an attacker-influenced upstream and a pipelining client.
