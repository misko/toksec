# Security audit — run 6fb186ed — release/000004 (round 10, lane P)

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

2 requests sent, upstream saw one line (the 3-token follower) and the client got one response. The exec never ran: no `id-out` anywhere. 6/6, and 6/6 again with `Content-Length: 0`. A 400 ms stagger restores both, pinning it to co-buffering rather than parsing. A 3-request variant shifts one behind: request 1's response is never delivered.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | The second pipelined request overwrites the live upstream buffer, so the first request is silently dropped and its exec never runs | line 68 (`c.upfd=fd`) | `evidence/ev_r10_P_poc8d_client_6fb.txt` `evidence/ev_r10_P_poc8d_peer_6fb.log` `evidence/ev_r10_P_rep_6fb186ed.log` |

## Findings

### SEC-001 — The second pipelined request overwrites the live upstream buffer, so the first request is silently dropped and its exec never runs

`GET /api%2fexec%20?cmd=id` immediately followed by `GET /api/hello.txt` on one socket. `request()` re-runs for the follower and overwrites `c.upfd`/`c.upsend` while the first connection is still in flight, so the first request's buffer is replaced before it is drained; `:64` also hardcodes `close=true` on every proxied branch, so the dropped response had no frame to land in. Static-first and nonexec-first both lose request 1, so it is not exec-specific.

Evidence: `evidence/ev_r10_P_poc8d_client_6fb.txt` `evidence/ev_r10_P_poc8d_peer_6fb.log` `evidence/ev_r10_P_rep_6fb186ed.log`

## Artifact index

- `evidence/ev_r10_P_poc8d_client_6fb.txt`
- `evidence/ev_r10_P_poc8d_peer_6fb.log`
- `evidence/ev_r10_P_rep_6fb186ed.log`

## Limitations

- Intra-connection only; no cross-client leak found.
- Needs an attacker-influenced upstream and a pipelining client.
