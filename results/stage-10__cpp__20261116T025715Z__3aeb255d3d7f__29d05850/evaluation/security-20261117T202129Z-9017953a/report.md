# Security audit — run 29d05850 — release/000002 (round 9, lane I)

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
| SEC-001 | yes | low | Every 1xx is rejected outright: 23 of 23 interim shapes returned 502 and no interim head ever reaches the client | line 57 (`code<200`) | `evidence/ev_r9_I_client_29d05850.txt` |

## Findings

### SEC-001 — Every 1xx is rejected outright: 23 of 23 interim shapes returned 502 and no interim head ever reaches the client

The response parser marks code<200 as bad, so a 100/103/101/199 from the upstream is a proxy error rather than a forward. A backend that answers 100-continue style is unusable through this proxy. Precondition: any upstream that emits an interim response.

Evidence: `evidence/ev_r9_I_client_29d05850.txt`

## Artifact index

- `evidence/ev_r9_I_client_29d05850.txt`

## Limitations

- Upstream-host execution only; the proxy itself runs nothing.
- The attack needs an attacker-influenced or malicious upstream, which is the normal case for a
  reverse proxy in front of a third-party service.
