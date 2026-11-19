# Stage 2: concurrent persistent HTTP

Header field values are opaque bytes and need not be UTF-8; the shared prohibitions on NUL, malformed lines and folded headers still apply.
Support GET and HEAD. For HEAD return the same status and representation headers as GET, including the GET Content-Length, with no body.
HTTP/1.1 persists by default; Connection: close overrides it. HTTP/1.0 closes by default and need not support keep-alive. Include Connection: keep-alive or close explicitly.
Parse Connection tokens case-insensitively. Handle sequential requests and up to pipeline_depth pipelined requests in order. A response body must never be confused with the next header.
Close after max_requests responses, advertising close on the final response. Close idle connections after idle_timeout_ms. An incomplete request has its own absolute header deadline from its first byte; idle waiting uses the idle deadline.
Malformed requests return their error then close. GET and HEAD bodies remain forbidden. Backpressure must bound queued requests and response data; pause reads rather than grow queues beyond pipeline_depth.
Serve concurrent clients independently. Slow input or output on one connection must not block ordinary clients. Enforce max_connections and write_timeout_ms. Refuse or close excess connections without crashing.

The shared HTTP file-serving requirements apply. This is an independent task,
not an extension of a supplied Stage 1 implementation.

Configuration limits are behavioral requirements, not fixed fixture constants.
The evaluator may lower max_connections, pipeline_depth, or write_timeout_ms.
A legal pipeline longer than pipeline_depth must be processed in order using
backpressure, rather than rejected merely because the burst exceeds the queue
bound. Other clients must remain serviceable while that pipeline is blocked.
A write that makes no progress for write_timeout_ms must close the connection
and release its slot. Test with responses larger than socket buffers and clients
that stop reading. Internal queue size cannot be proved by finite black-box tests.
