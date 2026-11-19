# Security audit — run 063b0d5e — release/000002 (round 9, lane I)

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
| SEC-001 | yes | medium | An interim head's Content-Length is applied to the real response body, so the upstream chooses the bytes the client receives | line 71 (`respleft`) | `evidence/ev_r9_I_poc_c20_c20.hex` |
| SEC-002 | yes | low | The interim loop never skips an interim body, so 101, a 100 carrying a body, and a ninth interim are all 502 | line 69 (`continue;`) | `evidence/ev_r9_I_client_063b0d5e.txt` |

## Findings

### SEC-001 — An interim head's Content-Length is applied to the real response body, so the upstream chooses the bytes the client receives

The 1xx branch loops back to parse a second head, but respleft from the interim head is left live; when the real 200 arrives its body is emitted only up to the interim length, and the interim head is stamped with that same Content-Length. An upstream that sends 100 with Content-Length: 100 replaces the client's HELLO with whatever bytes follow, and the client sees a Content-Length that does not describe its body. Precondition: an attacker-influenced upstream and a proxied location.

Evidence: `evidence/ev_r9_I_poc_c20_c20.hex`, `evidence/ev_r9_I_poc_ctl_c20.hex`

### SEC-002 — The interim loop never skips an interim body, so 101, a 100 carrying a body, and a ninth interim are all 502

The loop continues as soon as a head parses and never consumes bytes belonging to the interim response, so any interim that carries a body desynchronises the parse and the client gets 502. Concretely 101 with Upgrade, 100 followed by body bytes, and nine consecutive interims were each 502 on this build. Precondition: an attacker-influenced upstream.

Evidence: `evidence/ev_r9_I_client_063b0d5e.txt`

## Artifact index

- `evidence/ev_r9_I_poc_c20_c20.hex`
- `evidence/ev_r9_I_poc_ctl_c20.hex`
- `evidence/ev_r9_I_client_063b0d5e.txt`

## Limitations

- Upstream-host execution only; the proxy itself runs nothing.
- The attack needs an attacker-influenced or malicious upstream, which is the normal case for a
  reverse proxy in front of a third-party service.
