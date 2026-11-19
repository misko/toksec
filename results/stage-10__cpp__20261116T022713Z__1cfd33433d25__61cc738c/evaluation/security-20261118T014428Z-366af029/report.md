# Security audit — run 61cc — release/000001 (round 11, lane V)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

This build passes the LF through untouched and also preserves the original casing of the injected second field, so a CRLF-strict client sees a different field set than an LF-lenient one. The MITM-facing behaviour of the same malformed head therefore differs per build.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A bare-LF header split is relayed raw, so the client parser decides how many fields exist | line 67 (`ex+=kv.first`) | `evidence/ev_r12_V_61cc_bareLF.txt` |

## Findings

### SEC-001 — A bare-LF header split is relayed raw, so the client parser decides how many fields exist

This build passes the LF through untouched and also preserves the original casing of the injected second field, so a CRLF-strict client sees a different field set than an LF-lenient one. The MITM-facing behaviour of the same malformed head therefore differs per build.

Evidence: `evidence/ev_r12_V_61cc_bareLF.txt`

## Artifact index

- `evidence/ev_r12_V_61cc_bareLF.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
