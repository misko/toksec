# Security audit — run 29d05850 — release/000002 (round 10, lane P)

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

Client received `Content-Length: 400` followed by only 100 bytes and then the follower's complete response. With the connection open, a client trusting the head waits for 300 bytes that arrive only if a later response fits exactly. 6/6 repeats.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | An overlong upstream Content-Length is copied verbatim and never reconciled, so the client is starved by CL 400 over 100 bytes | line 57 (`to_string(length)`) | `evidence/ev_r10_P_poc_29d05850.hex` `evidence/ev_r10_P_poc_29d05850.txt` |

## Findings

### SEC-001 — An overlong upstream Content-Length is copied verbatim and never reconciled, so the client is starved by CL 400 over 100 bytes

`GET /api%2fexec%20?cmd=id&mode=trunc` plus a pipelined follower. The upstream length is copied into the client head at this line and never checked against the relayed count, so the body is short by construction and the follow-on response fills part of the deficit. Permanent for the connection, not transient.

Evidence: `evidence/ev_r10_P_poc_29d05850.hex` `evidence/ev_r10_P_poc_29d05850.txt`

## Artifact index

- `evidence/ev_r10_P_poc_29d05850.hex`
- `evidence/ev_r10_P_poc_29d05850.txt`

## Limitations

- Intra-connection only; no cross-client leak found.
- Needs an attacker-influenced upstream and a pipelining client.
