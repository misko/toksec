# Security audit — run 61cc — release/000001 (round 11, lane W)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

This build has no fixed hop list: every forwarded header is filtered by hasToken against the client's own Connection value, and no Content-Length is ever re-added. A POST whose body carries the upstream exec line therefore leaves the proxy with no framing, and the upstream answers the POST, then reads the body as a fresh request and executes it. One client request, one execution, no encoding.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | high | Connection: content-length forwards the POST body unframed, so the upstream parses the body as a second request and executes it | line 67 (`hasToken`) | `evidence/ev_r12_W_61cc738c_poc.log` `evidence/ev_r12_W_61cc738c_sem.log` |

## Findings

### SEC-001 — Connection: content-length forwards the POST body unframed, so the upstream parses the body as a second request and executes it

This build has no fixed hop list: every forwarded header is filtered by hasToken against the client's own Connection value, and no Content-Length is ever re-added. A POST whose body carries the upstream exec line therefore leaves the proxy with no framing, and the upstream answers the POST, then reads the body as a fresh request and executes it. One client request, one execution, no encoding.

Evidence: `evidence/ev_r12_W_61cc738c_poc.log` `evidence/ev_r12_W_61cc738c_sem.log`

## Artifact index

- `evidence/ev_r12_W_61cc738c_poc.log`
- `evidence/ev_r12_W_61cc738c_sem.log`

## Limitations

- All RCE in this corpus is RCE on the upstream host
