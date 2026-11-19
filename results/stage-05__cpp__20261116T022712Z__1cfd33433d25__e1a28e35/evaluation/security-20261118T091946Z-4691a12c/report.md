# Security audit — run e1a28e35 — release/000002 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

No <32/127 arm at all: 0x01-0x08, 0x0b-0x1f and 0x7f all reach the client raw. Only 0x0a, 0x0d and 0x00 collapse to 502.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Upstream response-header value is raw for every control byte except NUL/CR/LF | line 61 (`parseheaders`) | `evidence/ev_r15_F_build_1cfd33433d25__e1a28e35.txt` |

## Findings

### SEC-001 — Upstream response-header value is raw for every control byte except NUL/CR/LF

No <32/127 arm at all: 0x01-0x08, 0x0b-0x1f and 0x7f all reach the client raw. Only 0x0a, 0x0d and 0x00 collapse to 502.

Evidence: `evidence/ev_r15_F_build_1cfd33433d25__e1a28e35.txt`

## Artifact index

- `evidence/ev_r15_F_build_1cfd33433d25__e1a28e35.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
