# Security audit — run 44bf7f35 — release/000001 (round 11, lane R)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Negative with a clean outcome: `HTTP/1.1 417 Expectation Failed`, `Content-Length: 0`, `Connection: close`, `eof` at 0.000 s, nothing after it and no upstream contact. All six value shapes (case, unknown token, padded, duplicate, empty, plus chunked) collapse to the identical 417, so the value is never inspected. The socket dies with the response, so the unconsumed body is discarded rather than re-parsed.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | `Expect: 100-continue` is refused with a bare 417 that closes the socket, so the body after it is dead but nothing is desynced | line 90 (`bad(417)`) | `evidence/ev_r11_R_44bf_p417.txt` |

## Findings

### SEC-001 — `Expect: 100-continue` is refused with a bare 417 that closes the socket, so the body after it is dead but nothing is desynced

Negative with a clean outcome: `HTTP/1.1 417 Expectation Failed`, `Content-Length: 0`, `Connection: close`, `eof` at 0.000 s, nothing after it and no upstream contact. All six value shapes (case, unknown token, padded, duplicate, empty, plus chunked) collapse to the identical 417, so the value is never inspected. The socket dies with the response, so the unconsumed body is discarded rather than re-parsed.

Evidence: `evidence/ev_r11_R_44bf_p417.txt`

## Artifact index

- `evidence/ev_r11_R_44bf_p417.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
