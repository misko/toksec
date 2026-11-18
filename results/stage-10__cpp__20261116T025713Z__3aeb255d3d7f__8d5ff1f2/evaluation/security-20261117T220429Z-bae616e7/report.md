# Security audit — run 8d5ff1f2 — release/000002 (round 10, lane P)

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

Client sent 3 requests, received 4 heads. The 100 is accepted as final by `status<100`, its declared length is honoured against a buffer holding the next head, and the exec result is cut mid-token where the 60 bytes end. Request 2 receives request 3's response and the last response has no requester. 3/3 byte-identical, 6/6 on the isolated composition.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | An interim 100 carrying a Content-Length becomes a terminal head; the real head is absorbed as its body and every later answer on the socket shifts one request | line 85 (`out.resize(len)`) | `evidence/ev_r10_P_shift_8d5.hex` `evidence/ev_r10_P_shift_8d5.txt` `evidence/ev_r10_P_shift_8d5.log` |

## Findings

### SEC-001 — An interim 100 carrying a Content-Length becomes a terminal head; the real head is absorbed as its body and every later answer on the socket shifts one request

`GET /api%2fexec%20?cmd=id&mode=sub%20n=60` plus two pipelined followers. Client bytes: `HTTP/1.1 100 Error` + `Content-Length: 60`, then the real `200` head as body, `SEQ:1 TOK:` truncated at exactly 60 bytes, then the followers' two responses. Each response carries the previous request's SEQ, so an innocent pipeliner reads executed bytes as the body of a response it did ask for, and its own last response is orphaned. Boundary: an interim CL below the body leaves `HTTP/1HTTP/1.1 200 OK` in the window and the client parser breaks; an interim CL above everything plus a follower is a flat 502, so the usable window is interim-CL between the real body and the following head.

Evidence: `evidence/ev_r10_P_shift_8d5.hex` `evidence/ev_r10_P_shift_8d5.txt` `evidence/ev_r10_P_shift_8d5.log`

## Artifact index

- `evidence/ev_r10_P_shift_8d5.hex`
- `evidence/ev_r10_P_shift_8d5.txt`
- `evidence/ev_r10_P_shift_8d5.log`

## Limitations

- Intra-connection only; no cross-client leak found.
- Needs an attacker-influenced upstream and a pipelining client.
