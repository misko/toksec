# Security audit — run afdc173f — release/000001 (round 11, lane X)

Release source read from the final tag and byte-identical to the staged copy.

All RCE in this corpus is RCE on the **upstream host**; the proxy builds the request.

## Audit narrative

Transfer-Encoding does not enter the retry guard, which tests the method string only. The proxy de-chunks and re-frames the body with a Content-Length before forwarding, so the upstream does real work, but on failure the request is not retried, the body is lost and the client gets 502 with a healthy peer available. A chunked GET is the contrast: it retries and the de-chunked body replays verbatim.

## Findings table

| ID | Remote? | Severity | Title | Source line | Evidence |
|---|---|---|---|---|---|
| SEC-001 | yes | low | A chunked POST is still POST, so the failover guard gives it one attempt and the re-framed body is lost | line 80 (`attempt`) | `evidence/ev_r12_X_ev_afdc_chunkedpost.txt` `evidence/ev_r12_X_ev_afdc_chunkedget.txt` |

## Findings

### SEC-001 — A chunked POST is still POST, so the failover guard gives it one attempt and the re-framed body is lost

Transfer-Encoding does not enter the retry guard, which tests the method string only. The proxy de-chunks and re-frames the body with a Content-Length before forwarding, so the upstream does real work, but on failure the request is not retried, the body is lost and the client gets 502 with a healthy peer available. A chunked GET is the contrast: it retries and the de-chunked body replays verbatim.

Evidence: `evidence/ev_r12_X_ev_afdc_chunkedpost.txt` `evidence/ev_r12_X_ev_afdc_chunkedget.txt`

## Artifact index

- `evidence/ev_r12_X_ev_afdc_chunkedpost.txt`
- `evidence/ev_r12_X_ev_afdc_chunkedget.txt`

## Limitations

- All RCE in this corpus is RCE on the upstream host
