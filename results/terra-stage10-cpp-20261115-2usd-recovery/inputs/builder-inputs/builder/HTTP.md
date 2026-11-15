# HTTP behavior

This is the complete Stage 10 HTTP subset. CONFIGURATION.md defines routing and
limit names; TLS.md changes transport, not application response semantics.

## Parsing and persistent connections

Accept HTTP/1.0 and HTTP/1.1 with CRLF framing and fragmented input. Reject other
versions, malformed request lines, bare LF, folded headers, NUL, invalid token
header names and prohibited control bytes in values with 400 then close. Header
values otherwise remain opaque bytes. An unknown syntactically valid method
returns 405. Support GET/HEAD locally and GET/HEAD/POST on proxy locations.
Requests containing Expect return 417 and close before forwarding a body;
Expect/100-continue negotiation is outside this subset.

HTTP/1.1 requires exactly one valid Host. HTTP/1.0 without Host uses the listener's
default virtual server. CONFIGURATION.md defines host normalization and unmatched
host behavior. Do not confuse SNI certificate selection with HTTP routing.

HTTP/1.1 is persistent unless Connection: close is present. HTTP/1.0 closes after
each response. Include an explicit Connection field. Parse its tokens without case
sensitivity. Serve sequential and pipelined requests in order. Pause input at the
configured pipeline limit rather than growing an unbounded request queue. Close
after keepalive_requests responses and advertise close on the final response.

Enforce absolute header and idle/write deadlines as specified in CONFIGURATION.md.
Header-size excess returns 431 then closes. A silent or stalled client cannot
prevent other clients progressing. Excess connections may be refused or closed.
Malformed clients and disconnects must not stop subsequent ordinary service.

## Local files

Split the query before decoding the path once as UTF-8. Reject malformed escapes,
invalid UTF-8, fragments, absolute-form targets, NUL and backslash with 400. Reject
decoded '..' components, any symlink component and nonregular files with 403.
Collapse repeated slashes and '.' components after decoding, before location selection.
Serve only immutable regular files confined beneath the selected root or alias.
Missing files return 404. A slash after a regular filename returns 403 or 404.

Reject local Transfer-Encoding, duplicate Content-Length, invalid lengths and
nonzero Content-Length with 400. A single decimal zero is accepted. Serve exact
bytes, including binary, empty and large files, with Content-Length and no
Transfer-Encoding. HEAD has GET's status and representation headers but no body.
Error bodies may be empty. MIME selection follows the configured types/default.

Directories without slash redirect with 301 and preserve the query. A trailing
slash selects the configured index if it is a regular file; otherwise return 403.
When etag is on, emit a stable quoted ETag. Matching If-None-Match or '*' returns 304 with ETag,
Content-Length: 0 and no body. With etag off, omit ETag and ignore If-None-Match. Check conditional handling before Range. Support a single bytes
range N-M, N- or -N on GET/HEAD; clamp the end to EOF. Return 206 and Content-Range
for satisfiable ranges, 416 with bytes */SIZE for unsatisfiable ranges, and 400 for
malformed or multiple ranges. All operations use the selected representation.

## Proxy framing and streaming

CONFIGURATION.md defines proxy_pass target construction and upstream selection.
Accept one Content-Length or one Transfer-Encoding: chunked, never both. Reject
duplicate lengths, unsupported transfer codings, malformed chunks or ambiguous
framing with 400. Decoded request bodies above the configured body limit return
413 before response commitment; close if a response is already committed.
Bound and validate trailers using the configured header limit; do not forward them.

Strip standard hop-by-hop fields and fields named by Connection in both
directions. Rewrite upstream Host to the chosen numeric endpoint authority.
Preserve end-to-end fields, status and exact decoded body. Reject malformed or
ambiguous upstream framing with 502 before commitment. Recognize Content-Length,
chunked and EOF-delimited upstream responses. HEAD never sends downstream body.
Discard at most eight informational 1xx responses before the final response;
101 switching protocols or excess informational responses produce 502. Apply the
header limit and upstream deadline while reading these responses. Final 204 and
304 responses have no body regardless of connection persistence. Omit framing
fields on 204. A valid Content-Length on 304 or HEAD describes representation
length only; never read that many body bytes. Never emit chunked framing on these
bodyless responses. A revalidation 304 is consumed by the cache logic in
OPERATIONS.md; otherwise forward 304 without body. Incompatible framing or
unsolicited bytes must not contaminate a later response.

Forward request/response body progress before the sender finishes. For known
lengths preserve Content-Length; for unknown lengths emit chunked HTTP/1.1 or
close-delimited HTTP/1.0. Never emit both Content-Length and Transfer-Encoding.
This explicitly replaces Stage 5's always-buffer-to-known-length proxy behavior.
Content-Length is still mandatory on local file responses.

On truncation, malformed framing, size excess or deadline after downstream headers
are committed, close without a successful chunk terminator or a second response.
Before commitment return 502 for upstream transport/framing failures and 504 for
upstream deadlines. Invalidate the failed upstream connection. Never return a
connection with unread body bytes to its reuse pool.

In a functional progress test, an upstream sends headers and a 64 KiB body prefix,
then waits for the client to acknowledge that prefix before sending the remainder.
The proxy must deliver the prefix within one second on an otherwise idle host.
Apply the equivalent test to uploads. Slow-reader tests verify bounded resource
usage and simultaneous small-request service; buffering whole large bodies is
not an acceptable streaming implementation.

Use bounded FIFO upstream admission and connection reuse. A full waiting queue
rejects new requests with 503 and Retry-After: 1. Queued requests expire at the
configured queue deadline with the same response. New arrivals/retries must not
overtake existing eligible waiters for the same upstream group. Do not retry POST.
Bodyless GET/HEAD may retry once on the next endpoint before downstream commitment.
Bound attempts to two total and preserve the original queue/attempt accounting.
Failures/cancellation release slots and cannot poison unrelated routes.
