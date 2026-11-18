# Security audit — run 61cc — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The upstream sends `Content-Length: 5` and `Transfer-Encoding: chunked` with a 15-byte chunk stream. The proxy relays the chunk framing verbatim but sizes its own emitted body from the Content-Length, so only the first 5 bytes of the chunk stream reach the client. A client that honours Transfer-Encoding reads a chunk size of 5 and then receives `HE` with no CRLF and no terminating zero chunk; the payload tail and the terminator never arrive. Silent under Connection: close, five of five cold replicates byte-identical with passing controls.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | A relayed response with both Transfer-Encoding: chunked and Content-Length is cut at the Content-Length while still chunk-framed | line 67 (`sendhead`) | `evidence/ev_r12_V_61cc_clTE_headline.txt` `evidence/ev_r12_V_61cc_clTE.txt` `evidence/ev_r12_V_61cc_dupCL.txt` |

## Findings

### SEC-001 — A relayed response with both Transfer-Encoding: chunked and Content-Length is cut at the Content-Length while still chunk-framed

The upstream sends `Content-Length: 5` and `Transfer-Encoding: chunked` with a 15-byte chunk stream. The proxy relays the chunk framing verbatim but sizes its own emitted body from the Content-Length, so only the first 5 bytes of the chunk stream reach the client. A client that honours Transfer-Encoding reads a chunk size of 5 and then receives `HE` with no CRLF and no terminating zero chunk; the payload tail and the terminator never arrive. Silent under Connection: close, five of five cold replicates byte-identical with passing controls.

Evidence: `evidence/ev_r12_V_61cc_clTE_headline.txt` `evidence/ev_r12_V_61cc_clTE.txt` `evidence/ev_r12_V_61cc_dupCL.txt`

## Artifact index

- `evidence/ev_r12_V_61cc_clTE_headline.txt`
- `evidence/ev_r12_V_61cc_clTE.txt`
- `evidence/ev_r12_V_61cc_dupCL.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
