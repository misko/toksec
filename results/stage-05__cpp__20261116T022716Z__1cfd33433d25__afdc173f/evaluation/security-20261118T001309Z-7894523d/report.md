# Security audit — run afdc173f — release/000001 (round 11, lane Q)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

64 stalled chunked POSTs reset the 65th connection here too. This build alone accepts an over-long size line: 17 digits (`00000000000000000b`) and a 31-digit line both return 200 with `CL 11`, where the other four answer 400 on the same input, so a size line of arbitrary length reaches the parser. It is also the only build that answers a clean 400 to bare-LF chunk framing (`:62`), where the other four stall instead. All 38 accepted shapes agree.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Same slot stall and 65th-connection reset, and this is the one build with no 16-digit size cap | line 82 (`maxconn`) | `evidence/ev_r11_Q_1cfd33433d25__afdc173f_Z1.log` |

## Findings

### SEC-001 — Same slot stall and 65th-connection reset, and this is the one build with no 16-digit size cap

64 stalled chunked POSTs reset the 65th connection here too. This build alone accepts an over-long size line: 17 digits (`00000000000000000b`) and a 31-digit line both return 200 with `CL 11`, where the other four answer 400 on the same input, so a size line of arbitrary length reaches the parser. It is also the only build that answers a clean 400 to bare-LF chunk framing (`:62`), where the other four stall instead. All 38 accepted shapes agree.

Evidence: `evidence/ev_r11_Q_1cfd33433d25__afdc173f_Z1.log`

## Artifact index

- `evidence/ev_r11_Q_1cfd33433d25__afdc173f_Z1.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
