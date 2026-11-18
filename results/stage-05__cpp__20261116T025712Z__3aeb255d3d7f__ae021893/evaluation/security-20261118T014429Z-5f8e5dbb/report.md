# Security audit — run ae02 — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

The upstream reader pairs every CR and LF and scans for NUL before accepting a head, so all malformed shapes are refused rather than relayed. Completes the two refuse-complete builds against the three pass-raw ones.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | informational | Explicit CR/LF pairing and NUL scanning make this the second refuse-complete build | line 64 (`upstream`) | `evidence/ev_r12_V_extract_ae02.txt` |

## Findings

### SEC-001 — Explicit CR/LF pairing and NUL scanning make this the second refuse-complete build

The upstream reader pairs every CR and LF and scans for NUL before accepting a head, so all malformed shapes are refused rather than relayed. Completes the two refuse-complete builds against the three pass-raw ones.

Evidence: `evidence/ev_r12_V_extract_ae02.txt`

## Artifact index

- `evidence/ev_r12_V_extract_ae02.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
