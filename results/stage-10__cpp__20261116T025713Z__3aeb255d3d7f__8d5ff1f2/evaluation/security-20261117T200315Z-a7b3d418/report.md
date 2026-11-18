# Security audit — run 8d5ff1f2 — release/000002 (round 8, lane F)

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
| SEC-001 | yes | high | Host/SNI authority split | line 81 (`static int sni_cb`) | `evidence/ev_r8_F_8d5_evidence.txt` |
| SEC-002 | yes | high | Host/SNI authority split | line 87 (`if(!srv`) | `evidence/ev_r8_F_8d5_final2.log` |
| SEC-003 | yes | high | Host/SNI authority split | line 85 (`Host: 127.0.0.1:`) | `evidence/ev_r8_F_8d5_evidence.txt` |
| SEC-004 | yes | medium | Host/SNI authority split | line 42 (`validate_nodes`) | `evidence/ev_r8_F_8d5_cnrt.log` |
| SEC-005 | yes | medium | Host/SNI authority split | line 53 (`validhost(a`) | `evidence/ev_r8_F_8d5_evidence.txt` |
| SEC-006 | yes | medium | Host/SNI authority split | line 75 (`static bool validhost`) | `evidence/ev_r8_F_8d5_evidence.txt` |

## Findings

### SEC-001 — `static int sni_cb` (line 81)

The SNI callback sets only the certificate and never the route, so the two authorities are independent on this build too.

Evidence: `evidence/ev_r8_F_8d5_evidence.txt`

### SEC-002 — `if(!srv` (line 87)

SNI beta.test plus Host alpha.test yields beta's certificate, a passing hostname verify, and execution on alpha's proxied route in a single request.

Evidence: `evidence/ev_r8_F_8d5_final2.log`

### SEC-003 — `Host: 127.0.0.1:` (line 85)

The upstream Host is the constant 127.0.0.1:<port>; client Host is routing-only.

Evidence: `evidence/ev_r8_F_8d5_evidence.txt`

### SEC-004 — `validate_nodes` (line 42)

validate_nodes() contains the server_name checks but load() never calls it, so every name check in the function is dead code on this build.

Evidence: `evidence/ev_r8_F_8d5_cnrt.log`

### SEC-005 — `validhost(a` (line 53)

The validhost() call inside validate_nodes never executes at load time, which is why malformed names are accepted and then unreachable.

Evidence: `evidence/ev_r8_F_8d5_evidence.txt`

### SEC-006 — `static bool validhost` (line 75)

The Host validator itself is strict (rejects trailing dot, underscore, wildcard), which is why the names accepted by the dead validator cannot be routed to.

Evidence: `evidence/ev_r8_F_8d5_evidence.txt`

## Artifact index

- `evidence/ev_r8_F_8d5_evidence.txt`
- `evidence/ev_r8_F_8d5_final2.log`
- `evidence/ev_r8_F_8d5_cnrt.log`

## Limitations

- Upstream-host execution only; an exec-capable proxied location is required to turn the split
  into command output.
- Requires a TLS listener with at least two server blocks.
