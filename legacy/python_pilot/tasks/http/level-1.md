# HTTP Level 1 contract, version 1

Implement a restricted static HTTP server from an empty implementation directory. This task is a deliberately limited HTTP profile, not a claim of full HTTP conformance.

## Implementation and process interface

- Deliver one UTF-8 Python 3 file named `server.py`, at most 1 MiB.
- Use Python standard-library primitives. Do not use `http`, `http.server`, `http.client`, `wsgiref`, third-party web frameworks, installed server binaries, or delegated server implementations. URL parsing and filesystem helpers are permitted.
- Launch with `python3 -I -B server.py --host 127.0.0.1 --port PORT --root DIRECTORY`.
- Bind the supplied address and port within two seconds. Remain alive for subsequent connections.
- Serve immutable test files. Files are not modified during an evaluation.
- The evaluator supplies 256 MiB address space, a 15-second CPU limit per process, and a 45-second overall evaluation deadline. Sequential service is permitted.
- No network downloads or subprocess-based server delegation. No persistence or writes to the document root.

## Requests

- Accept `GET SP origin-target SP HTTP/1.0 CRLF` and `GET SP origin-target SP HTTP/1.1 CRLF`, followed by zero or more well-formed header lines and a final CRLF.
- This restricted profile permits requests without `Host` for both accepted versions. Do not add virtual-host routing.
- Read a request across arbitrary TCP fragments. Do not assume one `recv` contains a complete request.
- Header names are nonempty HTTP token characters. Header lines require a colon. Leading whitespace, embedded NUL, and bare LF are malformed.
- Header names are case-insensitive. Ignore well-formed unrecognized headers.
- Reject unsupported versions, malformed request lines, invalid percent escapes, fragments in targets, absolute-form targets, and malformed headers with 400.
- Reject `Transfer-Encoding`, multiple `Content-Length` fields, invalid lengths, and nonzero `Content-Length` with 400. A single `Content-Length: 0` is permitted.
- For syntactically valid unsupported methods without a body, return 405. Only GET is supported.
- Read no more than 8192 header bytes including the terminating CRLF pair. Return 431 and close when this limit is exceeded.
- Close incomplete requests within one second of accepting the connection. A 408 response is optional. The evaluator allows a scheduling margin.
- Process at most one request per connection. Ignore trailing pipelined requests by closing after the first response.

## Paths and files

- Strip the query string before resolving the path. Query bytes do not change file selection.
- Percent-decode the path exactly once using strict escapes and UTF-8. Return 400 for invalid UTF-8, NUL, or backslash.
- Return 403 if any decoded path component is `..`, or any existing path component is a symbolic link.
- Resolve valid paths beneath the supplied root. Never serve a file outside that root.
- Serve only regular files. Directories and other existing nonregular objects return 403. Missing paths return 404.
- A path with a trailing slash must not serve a regular file. Return 403 or 404.
- Preserve bytes exactly, including zero-length files, binary data, and files of at least 2 MiB. Do not append a newline.

## Responses

- Emit an HTTP/1.0 or HTTP/1.1 status line, CRLF-separated headers, an empty line, and the body.
- Include exactly one valid decimal `Content-Length`, matching the response body size.
- Include `Connection: close`. Do not use `Transfer-Encoding`.
- A successful file response has status 200. Error bodies may be empty and are otherwise unspecified.
- For successful responses, `Content-Type: application/octet-stream` is sufficient. MIME detection is not required.
- Close the connection after sending the response. A client must be able to observe EOF.
- Malformed requests and client disconnects must not prevent later valid requests from succeeding.

## Development and acceptance

Start with an externally tested file-serving path. Request promotion after each meaningful change. A controller evaluation is authoritative for promotion.

Capability groups are `bootstrap`, `files`, `paths`, `framing`, `limits`, and `recovery`. Every group must pass for promotion-suite conformance. Bootstrap requires ordinary, empty, and missing-file cases.

Before full conformance, preserve all previously passed groups. After full conformance, measure valid requests per second for repeated 4 KiB GETs on new TCP connections. Three rounds of 100 requests are used. Correct responses and EOF are required for every counted request. Each complete ordinary request must finish within three seconds. There is no uncalibrated throughput floor.

This evaluator does not establish absence of exploits. Attack evaluation and sealed final conformance are separate future work.
