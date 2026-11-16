# Proxy requirements

For paths beneath proxy_prefix, strip the prefix and send an origin-form '/' plus the remainder to the upstream, preserving the query. Local routes retain their Level 3 semantics.
Proxy GET, HEAD and POST. Permit a single valid Content-Length body or Transfer-Encoding: chunked, but never both. Reject duplicate lengths, unsupported transfer codings and invalid chunk syntax with 400. Decoded bodies above body_bytes return 413. Decode chunks and optional bounded trailers; do not forward trailers.
Use round-robin upstream selection for consecutive healthy requests. Reuse healthy HTTP/1.1 upstream connections. Strip hop-by-hop headers and every header named by Connection in both directions. Rewrite Host to the selected upstream authority.
Forward end-to-end headers, status and exact decoded body. Upstream Content-Length and chunked bodies are supported. Emit a known Content-Length downstream; bound response bodies to body_bytes, returning 502 if exceeded. HEAD has no downstream body.
Reject ambiguous or malformed upstream framing with 502. Apply upstream_timeout_ms to connection and response completion. A GET/HEAD may retry once on the next upstream only before a downstream response begins. Never retry POST. Final transport/malformed failures return 502; final deadline expiry returns 504.
Keep downstream request/response order. Upstream failures and disconnected downstream clients must not leak unbounded connections or poison subsequent requests.
