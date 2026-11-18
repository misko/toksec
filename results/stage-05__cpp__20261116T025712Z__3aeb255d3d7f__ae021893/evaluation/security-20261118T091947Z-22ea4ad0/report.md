# Security audit — run ae021893 — release/000001 (round 11, lane F)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Pairs driven on the decoded branch. Of nine pairs only LF-bearing ones are parsed at all, and only as HTTP/0.9 with a lossy target; HTAB-bearing pairs 400. nginx 1.28.3 is the reference consumer. Primitive, not a second-request smuggle.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | medium | Decoded pair backslash-x0a-backslash-x0d reaches the upstream request line and demotes the upstream parse to HTTP/0.9 | line 64 (`upstream`) | `evidence/ev_r15_F_pairs_ae.json` `evidence/ev_r15_F_nginx_verdict.json` |

## Findings

### SEC-001 — Decoded pair backslash-x0a-backslash-x0d reaches the upstream request line and demotes the upstream parse to HTTP/0.9

Pairs driven on the decoded branch. Of nine pairs only LF-bearing ones are parsed at all, and only as HTTP/0.9 with a lossy target; HTAB-bearing pairs 400. nginx 1.28.3 is the reference consumer. Primitive, not a second-request smuggle.

Evidence: `evidence/ev_r15_F_pairs_ae.json` `evidence/ev_r15_F_nginx_verdict.json`

## Artifact index

- `evidence/ev_r15_F_pairs_ae.json`
- `evidence/ev_r15_F_nginx_verdict.json`

## Limitations

- All RCE in this corpus is RCE on the upstream host
