# Security audit — run 6baf167b — release/000001 (round 11, lane Q)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Four shapes leave the decoder waiting with no upstream contact and no status — a `0` terminator without its final CRLF, an over-declared size with the terminator following, a bare `\r` terminator, and the same three on a keep-alive socket. The socket then closes with zero bytes at `header_timeout` (1.00 s measured with `header_timeout_ms=1000`, i.e. 20x sooner than `idle_timeout_ms=20000` implied). 64 of these concurrently fill `maxconn` and the 65th connection is reset. All 36 accepted shapes re-emit an honest `Content-Length` equal to the emitted byte count, so this is not a smuggle.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Stalled chunked bodies hold their connection slot past the header deadline, and 64 of them reset the 65th client | line 110 (`maxconn`) | `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log` |

## Findings

### SEC-001 — Stalled chunked bodies hold their connection slot past the header deadline, and 64 of them reset the 65th client

Four shapes leave the decoder waiting with no upstream contact and no status — a `0` terminator without its final CRLF, an over-declared size with the terminator following, a bare `\r` terminator, and the same three on a keep-alive socket. The socket then closes with zero bytes at `header_timeout` (1.00 s measured with `header_timeout_ms=1000`, i.e. 20x sooner than `idle_timeout_ms=20000` implied). 64 of these concurrently fill `maxconn` and the 65th connection is reset. All 36 accepted shapes re-emit an honest `Content-Length` equal to the emitted byte count, so this is not a smuggle.

Evidence: `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log`

## Artifact index

- `evidence/ev_r11_Q_1cfd33433d25__6baf167b_Z1.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
