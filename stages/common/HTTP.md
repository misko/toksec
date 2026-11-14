# Shared static-file HTTP requirements

A valid unknown method returns 405. Missing Host is permitted in this restricted profile. Versions other than 1.0 and 1.1 return 400.
Read fragmented requests and require CRLF. Reject bare LF, NUL, invalid header names, folded headers, malformed request lines and malformed headers with 400.
Reject Transfer-Encoding, duplicate Content-Length, invalid lengths and nonzero Content-Length with 400. A single decimal zero, including leading zeroes, is accepted.
Enforce header_bytes including the final CRLFCRLF; excess returns 431.
Strip the query, decode path percent escapes once as UTF-8, reject malformed escapes, fragments, absolute-form, NUL and backslash with 400.
Return 403 for decoded '..' components, symlinks in any component, directories and nonregular files. Missing files return 404. Trailing slash on a regular file returns 403 or 404.
Serve immutable regular files only beneath root. Preserve exact bytes for empty, binary and large files. Explicit Content-Length is mandatory and must match body bytes. No Transfer-Encoding in local responses.
Error bodies may be empty. Successful local responses may use application/octet-stream. Disconnects and malformed clients must not stop later valid service.
