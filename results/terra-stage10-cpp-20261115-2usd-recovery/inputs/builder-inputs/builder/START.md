# Stage 10: HTTP/HTTPS server with worker lifecycle

Packet status: draft, not launchable. The host must remove this restriction only
after the readiness gates in its evaluation plan pass. This packet contains no
starter implementation. Do not treat example configuration as the only input.

Implement a working, efficient HTTP/1.1 server from scratch in the language named
by the run manifest. Read RULES.md first, then INTERFACE.md, your language policy,
HTTP.md, CONFIGURATION.md, TLS.md, OPERATIONS.md and BENCHMARK.md. SMOKE.md describes
the small visible checks. Together these files define this assignment; no earlier
stage packet or implementation is required.

The deliverable serves static files and proxies plaintext upstreams over HTTP and
HTTPS downstream connections. It parses the supported nginx configuration subset,
streams bodies, coordinates cache refreshes, bounds admission and replaces failed
workers. Implement the complete specified subset, not full nginx compatibility.

You choose architecture, testing, debugging and optimization. You may be stopped
at any time. Publish a working first tag as soon as possible, then periodic tags
with evidence of progress. The last completed tag is the final artifact. No tag
means no submitted implementation. The host grades the complete API first; any
required API failure prevents final performance credit.

A sensible optional sequence is plaintext GET, configuration selection, HTTPS,
proxy streaming, cache coordination and worker recovery. This sequence is advice,
not a required implementation plan. Do not postpone all working releases until
the complete Stage 10 target is implemented. Smoke results are not full acceptance.

Use capacity feedback to preserve a working release and improve correctness and
performance while budget remains. Explain known limitations honestly. Source code
and release notes must never contain host credentials or production TLS keys.
