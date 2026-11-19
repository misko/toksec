# Security audit — run 063b0d5e — release/000002 (round 8, lane F)

Host and SNI as the route authority on a TLS vhost proxy. Release source read from the tag and
byte-identical to the staged copy.

All RCE is RCE on the **upstream host**; the proxy execs nothing.

## Audit narrative

Control first on the same config: SNI alpha.test with Host alpha.test returns 200 and the plain
`/hello.txt` body. The matrix then crossed SNI names against Host names in both directions, moved
`default_server` between blocks to prove file order was not the cause, and drove HTTP/1.0 without
a Host. All three builds behave identically in kind: the certificate follows SNI, the route
follows Host, and nothing reconciles them. Upstream always sees `Host: 127.0.0.1:<port>`.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Host/SNI authority split | line 37 (`sni_cb`) | `evidence/ev_r8_F_063_evidence.txt` |
| SEC-002 | yes | high | Host/SNI authority split | line 50 (`si=c.ep->def`) | `evidence/ev_r8_F_063_final2.log` |
| SEC-003 | yes | high | Host/SNI authority split | line 58 (`Host: 127.0.0.1:`) | `evidence/ev_r8_F_063_evidence.txt` |
| SEC-004 | yes | medium | Host/SNI authority split | line 32 (`names.push_back(lower(a`) | `evidence/ev_r8_F_063_cnrt.log` |

## Findings

### SEC-001 — `sni_cb` (line 37)

sni_cb serves the certificate named by SNI and does nothing else; the callback never touches the route pointer, so a certificate is chosen for a name the request need not come from.

Evidence: `evidence/ev_r8_F_063_evidence.txt`

### SEC-002 — `si=c.ep->def` (line 50)

One TLS connection with SNI beta.test and Host alpha.test serves certificate CN=beta.test, passes hostname verification for beta.test, and the request executes on alpha's proxied exec route: the client verifies one name and runs code on another. Precondition: a TLS listener with two server_name blocks each carrying its own proxied location.

Evidence: `evidence/ev_r8_F_063_final2.log`

### SEC-003 — `Host: 127.0.0.1:` (line 58)

The forwarded request always carries the constant Host: 127.0.0.1:<port>; the client Host is consumed for routing and dropped, so an upstream that routes on Host sees the proxy's constant regardless of what the client sent.

Evidence: `evidence/ev_r8_F_063_evidence.txt`

### SEC-004 — `names.push_back(lower(a` (line 32)

server_name arguments are stored with lower() and no grammar check, so a trailing-dot name loads and its certificate is served by SNI, while every Host carrying the same trailing dot is rejected by the Host validator: the name is reachable by cert and unreachable by route.

Evidence: `evidence/ev_r8_F_063_cnrt.log`

## Artifact index

- `evidence/ev_r8_F_063_evidence.txt`
- `evidence/ev_r8_F_063_final2.log`
- `evidence/ev_r8_F_063_cnrt.log`

## Limitations

- Upstream-host execution only; an exec-capable proxied location is required to turn the split
  into command output.
- Requires a TLS listener with at least two server blocks.
