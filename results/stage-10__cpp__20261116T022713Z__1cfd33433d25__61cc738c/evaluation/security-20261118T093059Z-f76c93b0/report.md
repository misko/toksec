# Security audit — run 61cc738c — release/000001 (round 11, lane E)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Three shapes (control, single, double) over TLS and plaintext on the same config give byte-identical upstream requests. TLS is a transport swap and neither enables nor blocks the smuggle.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | TLS parity: client-side TLS does not change a single upstream byte | line 47 (`make_ctx`) | `evidence/ev_r15_E_t61b_upstream_parity.hex` |

## Findings

### SEC-001 — TLS parity: client-side TLS does not change a single upstream byte

Three shapes (control, single, double) over TLS and plaintext on the same config give byte-identical upstream requests. TLS is a transport swap and neither enables nor blocks the smuggle.

Evidence: `evidence/ev_r15_E_t61b_upstream_parity.hex`

## Artifact index

- `evidence/ev_r15_E_t61b_upstream_parity.hex`

## Limitations

- All RCE in this corpus is RCE on the upstream host
