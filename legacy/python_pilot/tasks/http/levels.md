# HTTP task levels

Levels are cumulative targets. An incomplete higher-level attempt is never relabeled as a successful lower-budget build of the higher level.

| Level | Scope | Status |
| --- | --- | --- |
| 1 | Static GET, fixed document root, one response per connection, bounded headers and read deadline | Concrete contract and promotion evaluator |
| 2 | Concurrent clients, HEAD, HTTP/1.1 persistent connections, ordered pipelining, bounded buffering | Roadmap only |
| 3 | Virtual hosts, exact and prefix routing, index files, redirects, MIME types, ETag, single ranges, startup configuration validation | Roadmap only |
| 4 | Reverse proxy, request bodies, chunked framing, upstream connection reuse, round-robin pools, timeouts, bounded retries | Roadmap only |
| 5 | TLS-library integration, SNI, proxy caching, revalidation, Vary, compression, rate limits, graceful reload and shutdown | Roadmap only |

Levels 2 through 5 need precise versioned contracts and tests before launch. They are not ready benchmark tasks. Full NGINX configuration compatibility, HTTP/2, HTTP/3, scripting, and dynamic modules are excluded.
