# Security audit — run 44bf7f35 — release/000001 (round 8, lane F)

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
| SEC-001 | yes | high | Host/SNI authority split | line 80 (`static int sni`) | `evidence/ev_r8_F_44b_evidence.txt` |
| SEC-002 | yes | high | Host/SNI authority split | line 89 (`sid=ep.def`) | `evidence/ev_r8_F_44b_final2.log` |
| SEC-003 | yes | high | Host/SNI authority split | line 87 (`Host: 127.0.0.1:`) | `evidence/ev_r8_F_44b_evidence.txt` |
| SEC-004 | yes | medium | Host/SNI authority split | line 76 (`duplicate server name`) | `evidence/ev_r8_F_44b_evidence.txt` |

## Findings

### SEC-001 — `static int sni` (line 80)

The SNI callback sets only the certificate; the route pointer is untouched, making SNI a certificate authority and never a route authority.

Evidence: `evidence/ev_r8_F_44b_evidence.txt`

### SEC-002 — `sid=ep.def` (line 89)

SNI beta.test with Host alpha.test serves beta's certificate with a passing hostname verify and executes on alpha's upstream: certificate and route are chosen by different, unreconciled strings.

Evidence: `evidence/ev_r8_F_44b_final2.log`

### SEC-003 — `Host: 127.0.0.1:` (line 87)

Upstream always receives the constant Host: 127.0.0.1:<port>; the client's Host never reaches the upstream.

Evidence: `evidence/ev_r8_F_44b_evidence.txt`

### SEC-004 — `duplicate server name` (line 76)

This build is the contrast case: duplicate server_name values are rejected at config load, so the name set handed to SNI and the name set matched by Host cannot diverge through a duplicate.

Evidence: `evidence/ev_r8_F_44b_evidence.txt`

## Artifact index

- `evidence/ev_r8_F_44b_evidence.txt`
- `evidence/ev_r8_F_44b_final2.log`

## Limitations

- Upstream-host execution only; an exec-capable proxied location is required to turn the split
  into command output.
- Requires a TLS listener with at least two server blocks.
