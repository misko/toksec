# Shared static-file HTTP requirements

A valid unknown method returns 405. Missing Host is permitted in Stages 1–2; Stages 3–5 use the routing Host requirements. Versions other than 1.0 and 1.1 return 400.
Read fragmented requests and require CRLF. Reject bare LF, NUL, invalid header names, folded headers, malformed request lines and malformed headers with 400.
On local file routes, reject Transfer-Encoding, duplicate Content-Length, invalid lengths and nonzero Content-Length with 400. A single decimal zero, including leading zeroes, is accepted.
Enforce header_bytes including the final CRLFCRLF; excess returns 431.
Strip the query, decode path percent escapes once as UTF-8, reject malformed escapes, fragments, absolute-form, NUL and backslash with 400.
Return 403 for decoded '..' components, symlinks in any component and nonregular files. Stages 1–2 reject directories with 403; Stages 3–5 use the routing index/redirect rules. Missing files return 404. Trailing slash on a regular file returns 403 or 404.
Local file routes serve immutable regular files beneath the selected root or alias. Preserve exact bytes for empty, binary and large files. Explicit Content-Length is mandatory and must match body bytes. No Transfer-Encoding in local responses.
Error bodies may be empty. Successful local responses may use application/octet-stream. Disconnects and malformed clients must not stop later valid service.
