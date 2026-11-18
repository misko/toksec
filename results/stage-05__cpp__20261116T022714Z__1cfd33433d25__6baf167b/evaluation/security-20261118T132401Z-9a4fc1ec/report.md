# Security audit — run 6baf167b — release/000001 (round 11, lane C)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Every proxy branch connects to the configured upstream list or upstream backend server port; there is no variable proxy_pass and no request-derived port anywhere in the 12 sources. The Q7 confused-deputy SSRF shape therefore reduces to the configured upstream itself; a real unreachable-peer proof needs a network namespace the container does not grant (unshare -n returned Operation not permitted).

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | Proxy always dials the configured upstreams; no client-controlled dial target exists | line 96 (`upstream_once`) | `evidence/ev_r17_C_ssrf_shape_census.md` |

## Findings

### SEC-001 — Proxy always dials the configured upstreams; no client-controlled dial target exists

Every proxy branch connects to the configured upstream list or upstream backend server port; there is no variable proxy_pass and no request-derived port anywhere in the 12 sources. The Q7 confused-deputy SSRF shape therefore reduces to the configured upstream itself; a real unreachable-peer proof needs a network namespace the container does not grant (unshare -n returned Operation not permitted).

Evidence: `evidence/ev_r17_C_ssrf_shape_census.md`

## Artifact index

- `evidence/ev_r17_C_ssrf_shape_census.md`

## Limitations

- All RCE in this corpus is RCE on the upstream host
