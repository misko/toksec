# Stage 10 configuration contract

Status: proposed builder reference. This packet is not runnable or published.
This file defines a restricted nginx configuration language and Toksec extensions.
It does not require full nginx compatibility. HTTP behavior is defined by `HTTP.md`.
TLS behavior is defined by `TLS.md`. Process and resource limits are defined by `INTERFACE.md`.

## Input and grammar

The entry point is `server --config /fixtures/config/nginx.conf`.
`server --check-config /fixtures/config/nginx.conf` performs the same complete validation without binding sockets or starting workers.
Success exits 0. Invalid input exits nonzero and reports the source file and one-based line to stderr without key contents.
Initial validation finishes before accepting connections. The implementation parses the configuration itself.

```text
configuration := statement*
statement     := word argument* ";" | word argument* "{" statement* "}"
argument      := bare | single_quoted | double_quoted
```

Input is UTF-8 without NUL or BOM. Keywords and enumerated values are case-sensitive ASCII.
Whitespace is space, tab, CR, or LF. A CRLF counts as one line and a lone CR is whitespace.
Outside quotes, `#` starts a comment through the next LF. `;`, `{`, and `}` are separate tokens.
A bare argument ends at whitespace, a delimiter, or `#`. Quotes must surround the whole argument.
Both quote forms permit whitespace, delimiters, and `#` literally, but prohibit raw CR and LF.
In all argument forms, backslash escapes backslash, either quote, space, tab, `#`, `;`, `{`, or `}` to that character.
The sequences `\n`, `\r`, and `\t` decode to LF, CR, and tab. Other escapes, dangling escapes, and unfinished quotes fail.
Decoded control characters are rejected by directive value grammars unless explicitly allowed. No directive below permits them in paths or names.
There is no variable substitution, environment expansion, quote concatenation, or shell execution. An argument containing `$` fails.
These lexical restrictions deliberately reject forms beyond this subset.

The expanded input has at most 1 MiB of source bytes, 16,384 statements, 4,096 bytes per decoded argument, and 32 arguments per statement.
At most 128 files may be opened per parse, counting repeated inclusions. Block depth is at most 8 and include depth at most 8 beyond the entry file.
All numeric values are unsigned decimal without sign, fraction, whitespace, or overflow.
`N` means 1 through 2^31-1. `Z` additionally permits zero. Directive-specific bounds override these ranges.
`SIZE` is `Z` optionally followed by `k` or `m`, multiplying by 1024 or 1048576, with a maximum of 2^31-1 bytes.
`TIME` is `N` optionally followed by `ms` or `s`. No suffix means seconds. The converted value must be at most 86,400,000 ms.

## Includes and contexts

`include PATH;` takes exactly one argument, is repeatable in every context, and expands statements in place.
Relative include paths resolve against the directory containing the entry configuration, never the including file's directory.
Absolute include paths must remain in that same configuration tree. Symlinks, `..` components, and nonregular files fail.
The only glob is `*`, matching zero or more filename bytes within the final path component, never `/` or a leading dot.
Matches expand in ascending UTF-8 byte order. A missing literal file fails. A glob with zero matches inserts no statements.
An include cycle on the active expansion stack fails. Repeated acyclic includes are parsed again and obey ordinary duplicate rules.
Included text inherits the caller's context and must contain complete statements. Blocks cannot cross file boundaries.

Contexts below are `M` main, `E` events, `H` http, `U` upstream, `S` server, and `L` location.
There must be exactly one `events {}` and one `http {}` in main, each with zero arguments.
`http` contains one or more `server {}` blocks and zero or more `upstream NAME {}` blocks.
Server blocks take zero arguments. Upstream names match `[A-Za-z_][A-Za-z0-9_]*` and must be unique.
`location PATH {}` and `location = PATH {}` occur only in server blocks. Nested locations are excluded.
Location paths start with `/`, contain no query, fragment, percent escapes, duplicate slash, `.` or `..` component, and are case-sensitive UTF-8.
One exact and one prefix location may share a path. Duplicate locations of the same kind fail.
Every server must declare a prefix `location /` as its fallback.
`types {}` is a zero-argument special mapping block permitted in H, S, and L.

## Native directive subset

Except where marked repeatable, each directive occurs at most once in its immediate context.
For directives permitted in H, S, and L, a child inherits its parent's value when absent and otherwise replaces it.
Other directives do not inherit unless stated. Every table row lists the complete accepted argument form.
Defaults apply after inheritance. The packet deliberately narrows accepted values, contexts, and optional parameters.

| Directive and arguments | Context | Default and meaning |
|---|---|---|
| `worker_processes 1\|2\|4` | M | `1`. Worker count, excluding the master. Immutable on reload. |
| `worker_connections N` | E | `512`. Per-worker active downstream plus upstream connections, including TLS handshakes and idle connections. |
| `listen 127.0.0.1:PORT [ssl] [default_server]` | S | Required, repeatable for distinct endpoints. PORT is 1..65535. Optional flags occur at most once in this order. |
| `server_name NAME...` | S | Required, 1..32 names. ASCII DNS labels, case-insensitive, no wildcard, regex, trailing dot, or underscore. |
| `root PATH` | H,S,L | `html` relative to the configuration prefix. Appends the complete normalized request path to this directory. |
| `alias PATH` | L | Absent. Only prefix locations ending in `/`, with an absolute directory PATH ending in `/`. Replaces the matched location prefix. |
| `index NAME...` | H,S,L | `index.html`. 1..32 plain filenames without slash, backslash, `.` or `..`. Try in order. |
| `default_type TYPE` | H,S,L | `text/plain`. TYPE is an ASCII media type `token/token` without parameters. |
| `etag on\|off` | H,S,L | `on`. Enables local representation ETags and conditional handling in HTTP.md. |
| `return 301\|302\|307\|308 DESTINATION` | L | Absent. Literal nonempty URI beginning `/`, `http://`, or `https://`, without whitespace or controls. |
| `keepalive_timeout TIME` | H,S,L | `75s`. Idle persistent downstream connection timeout. Also accepts literal `0` to disable persistence. |
| `keepalive_requests N` | H,S,L | `1000`. Maximum requests on one downstream connection. |
| `client_header_timeout TIME` | H,S | `60s`. Time allowed to receive the complete request header. |
| `client_body_timeout TIME` | H,S,L | `60s`. Maximum gap between downstream body reads. |
| `send_timeout TIME` | H,S,L | `60s`. Maximum gap between successful downstream writes. |
| `client_max_body_size SIZE` | H,S,L | `1m`. Maximum decoded request body. Zero removes this directive's cap; the Toksec body cap still applies. |
| `server 127.0.0.1:PORT` | U | Required, repeatable, distinct endpoints. At least one endpoint, at most 16. Equal-weight round robin. |
| `keepalive N` | U | No idle pool when absent. Maximum idle upstream connections per worker for this group, not an active-connection cap. |
| `proxy_pass http://NAME[/URI]` | L | Absent. NAME must name an upstream block. Literal URI starts `/` and contains no query, fragment, percent escapes, or variables. |
| `proxy_connect_timeout TIME` | H,S,L | `60s`. Connection-establishment deadline. |
| `proxy_read_timeout TIME` | H,S,L | `60s`. Maximum gap between upstream reads. |
| `proxy_send_timeout TIME` | H,S,L | `60s`. Maximum gap between upstream writes. |

`types` entries are `TYPE EXTENSION...;`, with 1..32 nonempty ASCII alphanumeric extensions per entry.
Extension matching is case-insensitive. Duplicate extensions in one mapping fail.
An absent block inherits the whole parent mapping. A present block replaces it, including an empty block.
The initial mapping is `text/html html; image/gif gif; image/jpeg jpg;`. Fixtures explicitly add `text/plain txt;`.
File paths resolve against the entry configuration directory when relative and must remain within supplied fixture or document roots.
`alias` and a local `root` cannot coexist. An alias overrides an inherited root. `return`, `proxy_pass`, and `alias` are mutually exclusive in one location.
A return or proxy location may inherit a root but does not serve files. Native directives omitted from this table or TLS.md fail explicitly.

An exact location wins. Otherwise the longest matching prefix wins. HTTP.md defines path normalization and confinement before matching.
An upstream URI on `proxy_pass` replaces the matched normalized location prefix, preserving the request query.
For example, `/api/a?x=1` under `location /api/` with `proxy_pass http://backend/;` becomes `/a?x=1`.
Without an upstream URI, the original request target is forwarded unchanged for accepted requests. Exact locations may also use URI replacement.
Return destinations are emitted literally without variable expansion or implicit query append. Directory redirects follow HTTP.md separately.
This target's strict Host validation and HTTP safety rules are separate from nginx compatibility.

## Toksec extension directives

Each extension takes one argument, occurs once in H only, has no inheritance, and applies across all workers and listeners unless stated.
Timers use monotonic time. These controls preserve benchmark semantics without assigning new meanings to nginx cache or rate directives.

| Directive | Grammar | Default and scope |
|---|---|---|
| `toksec_header_bytes` | SIZE, nonzero | `16k`. Complete request header limit. |
| `toksec_pipeline_depth` | N, at most 64 | `8`. Maximum outstanding requests per downstream connection. |
| `toksec_max_connections` | N | `8192`. Aggregate downstream connections, including handshakes. |
| `toksec_body_bytes` | SIZE, nonzero | `64m`. Decoded request and response body ceiling. |
| `toksec_header_deadline` | TIME | `2s`. Absolute deadline from first request byte. |
| `toksec_write_deadline` | TIME | `10s`. Absolute response deadline from first attempted downstream write. |
| `toksec_upstream_deadline` | TIME | `10s`. Absolute deadline across admission, all attempts, and response completion. |
| `toksec_upstream_active` | N | `256`. Aggregate active requests per upstream group. |
| `toksec_upstream_queue` | Z | `256`. Aggregate waiting requests per upstream group. |
| `toksec_upstream_queue_timeout` | TIME | `2s`. Absolute time in upstream admission queue. Expiry returns 503. |
| `toksec_cache_bytes` | SIZE | `32m`. Aggregate cached body bytes. Zero disables cache. |
| `toksec_cache_entries` | N | `4096`. Aggregate entry ceiling, partitioned equally among workers. |
| `toksec_cache_waiters` | N | `256`. Maximum waiting clients per cache key per worker. Excess returns 503 with Retry-After: 1. |
| `toksec_upstream_failures` | N | `3`. Consecutive transport/deadline failures before endpoint cooldown, across workers. |
| `toksec_upstream_cooldown` | TIME | `1s`. Endpoint exclusion interval, followed by one global probe. |
| `toksec_cache_ttl` | TIME | `5s`. Freshness lifetime ceiling. |
| `toksec_rate_per_second` | Z | `0`. Aggregate token refill rate. Zero disables rate limiting. |
| `toksec_rate_burst` | N | `100`. Aggregate token bucket capacity. |
| `toksec_drain_timeout` | TIME | `5s`. Maximum graceful shutdown duration. |
| `toksec_tls_handshake_timeout` | TIME | `2s`. Absolute deadline from accept through TLS handshake completion. |

When several deadlines apply, the earliest expiration wins. HTTP.md defines errors, retry, streaming, cache, and admission behavior.
The limiter bucket starts full. Each request consumes one token after complete valid headers, before cache lookup, upstream admission or body forwarding.
Validate bodies incrementally. A later malformed/oversized body or cancellation does not refund the token.
There is one bucket across HTTP and HTTPS, not one per worker, address, host, or client.
The rejected request receives 429 with `Retry-After: 1` and consumes no token.

## Selection and atomic reload

Servers may share an endpoint only if all agree on `ssl`. At most one is `default_server`.
Otherwise, the first server encountered after include expansion is the endpoint default.
Server names must be unique case-insensitively among servers sharing an endpoint.
HTTP Host matching uses only servers on the accepted endpoint. Unknown HTTP/1.1 hosts return 400 even when SNI matched.
Trim surrounding HTTP optional whitespace, then accept one ASCII DNS name with an optional decimal port from 1 through 65535.
Reject empty names, whitespace inside the value, IP literals, trailing dots, and invalid DNS labels with 400.
Remove the port and compare names case-insensitively. The port does not select another listener.
An unknown supplied Host returns 400 on either HTTP version.
HTTP/1.0 without Host uses the endpoint default. SNI certificate selection is independent, as specified in TLS.md.
Before Host is available, the endpoint default supplies header limits and timers. Request-specific settings apply after selection.

On SIGHUP the master reads and validates a complete candidate, including all includes, roots, and TLS material.
Listener endpoints, their `ssl` mode, worker count, worker_connections, upstream group names, and all toksec_* values except
toksec_rate_per_second, toksec_rate_burst and toksec_cache_ttl are immutable. Any change rejects the complete reload.
Upstream endpoints within an existing named group may change. Group-wide active/queue limits retain the same group identity
and count old and new generation reservations together. Endpoint cooldown/probe state is generation-specific.
The process-tree CPU, memory, descriptor and scratch budgets are fixed run-manifest limits, not reloadable configuration.
Root and alias targets must exist as readable directories at validation. Certificate and key files must be readable regular files.
The operator replaces fixture files before signaling and keeps the tree unchanged during candidate parsing.
The master commits one generation only after every worker can use it. Failure retains the complete previous generation and logs an error.
At commit, all cache entries are flushed and the aggregate limiter resets to a full bucket with the new settings.
Requests on old connections use this same current global bucket, while retaining old routing/TLS/request-timer settings.
Cache fills from old generations are disabled; their requests proxy normally and cannot repopulate either generation's cache.
Existing active/queued requests retain their reservations; reload does not grant them a second admission slot.
Connections accepted before commit retain their captured routing/configuration generation and close by the old generation's drain deadline. New connections use the committed generation. This differs explicitly from Stage 5 request-scoped reload.
Existing TLS connections retain their established TLS state. New accepts use the committed certificate generation.
Old generations remain alive only while needed by requests, connections, or bounded shutdown work.

Regex, rewrite, `if`, `map`, scripting, variables, DNS upstream resolution, Unix sockets, IPv6, arbitrary listen options, and disk caching are excluded.
`proxy_cache*` and `limit_req*` are excluded. Their semantics are not aliases for the extensions above.
Native directive meanings are checked against the nginx [core](https://nginx.org/en/docs/ngx_core_module.html), [HTTP core](https://nginx.org/en/docs/http/ngx_http_core_module.html), and [proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) references within the stated subset.
The release protocol must pin an nginx oracle version and build before this draft becomes an accepted task.
