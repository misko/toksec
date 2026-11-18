# Security audit — run 29d05850 — release/000002 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Every target parser requires target[0]==/ before any alias or proxy branch is reached, so GET http://host/path HTTP/1.1 can never reach the proxy branch and the absolute-form channel switch is closed by construction for this family.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Absolute-form target is a parse 400 on all 11 proxied builds | line 50 (`request`) | `evidence/ev_r17_C_absolute_form_census.md` |

## Findings

### SEC-001 — Absolute-form target is a parse 400 on all 11 proxied builds

Every target parser requires target[0]==/ before any alias or proxy branch is reached, so GET http://host/path HTTP/1.1 can never reach the proxy branch and the absolute-form channel switch is closed by construction for this family.

Evidence: `evidence/ev_r17_C_absolute_form_census.md`

## Artifact index

- `evidence/ev_r17_C_absolute_form_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
