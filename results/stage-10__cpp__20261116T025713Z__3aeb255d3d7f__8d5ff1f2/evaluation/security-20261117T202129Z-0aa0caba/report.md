# Security audit — run 8d5ff1f2 — release/000002 (round 9, lane I)

The interim (1xx) response state machine. Release source read from the tag and byte-identical to
the staged copy.

All RCE is RCE on the **upstream host**; the proxy execs nothing.

## Audit narrative

Control first on the same config: a plain 200 with Content-Length 5 returns HELLO on every build.
The peer then emitted, one path each, a 100 followed by a real 200, a 103 with a Link header, a
101 with Upgrade, a 100 carrying its own Content-Length and bytes, a truncated interim, a 199, two
100s, and a 100 followed by a chunked 200. Client bytes were captured as hex for every case and
compared against the control, then one follow-up request was sent on the same connection.

The split is clean: `063b0d5e` re-parses a second head but carries the interim length into the real
body, `8d5ff1f2` and `6fb186ed` treat the interim as terminal and truncate the real head, and
`29d05850` rejects every interim.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | A 1xx is treated as terminal and its Content-Length truncates the following real head mid-line | line 85 (`out.resize(len)`) | `evidence/ev_r9_I_poc_c30_c30.hex` |

## Findings

### SEC-001 — A 1xx is treated as terminal and its Content-Length truncates the following real head mid-line

The build keeps the first head and resizes the buffered output to the interim Content-Length, so the real 200 that follows is cut to that many bytes and arrives as body text: an interim Content-Length of 20 yields the tail HTTP/1.1 200 OK CRLF Con and nothing more. The client has a body that is a fragment of a head. Precondition: an attacker-influenced upstream.

Evidence: `evidence/ev_r9_I_poc_c30_c30.hex`, `evidence/ev_r9_I_poc_ctl_c30.hex`

## Artifact index

- `evidence/ev_r9_I_poc_c30_c30.hex`
- `evidence/ev_r9_I_poc_ctl_c30.hex`

## Limitations

- Upstream-host execution only; the proxy itself runs nothing.
- The attack needs an attacker-influenced or malicious upstream, which is the normal case for a
  reverse proxy in front of a third-party service.
