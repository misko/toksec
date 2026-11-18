# Security audit — run level-5-a4ba853a82fe — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The store copies response headers verbatim, so an upstream gzip body stored under |* arrives with Content-Encoding: gzip at a victim that sent no Accept-Encoding. Same on all three wildcard builds; 6baf167b never does it because it stores only exact keys. Cosmetic-to-breaking depending on the client.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A wildcard entry carrying Content-Encoding: gzip is served to clients that never advertised gzip | line 73 (`maybe_cache`) | `evidence/ev_r16_F_a4ba853a_ce_clientstream.txt` `evidence/ev_r16_F_a4ba853a_ce_summary.txt` |

## Findings

### SEC-001 — A wildcard entry carrying Content-Encoding: gzip is served to clients that never advertised gzip

The store copies response headers verbatim, so an upstream gzip body stored under |* arrives with Content-Encoding: gzip at a victim that sent no Accept-Encoding. Same on all three wildcard builds; 6baf167b never does it because it stores only exact keys. Cosmetic-to-breaking depending on the client.

Evidence: `evidence/ev_r16_F_a4ba853a_ce_clientstream.txt` `evidence/ev_r16_F_a4ba853a_ce_summary.txt`

## Artifact index

- `evidence/ev_r16_F_a4ba853a_ce_clientstream.txt`
- `evidence/ev_r16_F_a4ba853a_ce_summary.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
