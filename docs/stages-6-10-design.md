# Stages 6–10: nginx configuration and HTTPS

Status: proposed progression with an experimental Stage 10 implementation path.
Stages 6–9 do not yet have runnable stage profiles. Stage 10 now has a sandbox,
metered runner, partial independent checker, and [preserved results](../results/stage-10/cpp/README.md).
Full Stage 10 acceptance and calibrated performance grading remain incomplete.
Shared artifact contracts now apply to both runners; historical run inputs remain frozen.

A concrete [Stage 10 instruction and fixture packet](../stages/stage-10/README.md)
now provides language-specific prompt previews, draft contracts, example
configuration, test certificates and a hashed input allowlist. Its host readiness
plan records the original readiness requirements. The [runner documentation](../stage10/README.md)
describes current experimental support and the remaining grading limitations.

The user requested nginx configuration language and HTTPS/TLS in the progression.
This design makes those explicit stages before further streaming, caching, and
worker-lifecycle requirements. Each assignment remains independent and starts
without source code or another run's conversation. A published stage packet must
contain its complete inherited contract.

## Revised progression

| Stage | Complete target adds | Main evaluation |
|---|---|---|
| 6 | nginx configuration syntax and a defined directive subset, covering Stage 5 behavior | Parsing, contexts, inheritance, listener/host/location selection, configuration validation and atomic reload |
| 7 | HTTPS termination through approved OpenSSL, with HTTP/1.1 over TLS | Certificate identity, SNI, protocol negotiation, nonblocking handshakes, deadlines, reload and encrypted response correctness |
| 8 | Incremental large-body streaming and configurable upstream failure/admission policy | Forwarding progress, bounded memory, cancellation, retry rules and healthy-route isolation |
| 9 | Cache revalidation and shared misses | Validators, variant isolation, expiration, upstream request counts and waiter cancellation |
| 10 | Multiple workers and sustained mixed-workload operation | Worker replacement, shared limits, configuration/certificate generations, resource recovery and per-class service |

Stage 10 combines two substantial topics. Its implementation plan should expose
working worker-lifecycle and mixed-workload milestones without requiring a
particular agent development sequence. Stage numbers are complexity targets,
not an assertion that equal token budgets will complete each target.

## Stage 6 configuration language

Implement the parser in the submitted source. A wrapper that translates a few
fixture strings or delegates parsing to nginx is not allowed. The language has
semicolon-terminated directives, nested blocks, whitespace-separated arguments,
comments, quoted arguments and escapes. The final contract must enumerate exact
lexical behavior and size/depth limits rather than merely saying nginx-like.

Initial contexts are main, events, http, upstream, server and location. The
directive table must specify each supported directive's allowed contexts, arity,
default, value grammar, repetition rules, inheritance and reload behavior.

Proposed initial directive families:

- Structure and selection: events, http, server, upstream, listen, server_name,
  exact and prefix location, and include.
- Local files and redirects: root, alias, index, types, default_type and a
  restricted return form with literal status and destination.
- Connection behavior: worker_connections, keepalive_timeout,
  keepalive_requests, client_header_timeout, client_body_timeout, send_timeout,
  and client_max_body_size.
- Proxying: proxy_pass, upstream server entries, keepalive,
  proxy_connect_timeout, proxy_read_timeout and proxy_send_timeout.
- Existing cache and limiting behavior: a separately enumerated subset of
  proxy_cache_path, proxy_cache, proxy_cache_valid, limit_req_zone and limit_req.
  This requires a real semantics mapping; names alone do not provide compatibility.

Support literal server names, exact locations and longest-prefix locations first.
Regex locations, rewrite, if, map, scripting and arbitrary variable expressions
are outside the initial subset. Any required variables for cache/rate-limit
directives must be explicitly listed, with evaluation rules and rejection of
unsupported expressions. Do not silently implement a directive with meaning that
differs from nginx under the same name.

Resolve include paths against a declared configuration prefix. Publish the exact
supported glob grammar, ordering, nesting limits and cycle behavior. Mount only
the configuration fixture tree and other explicitly required sandbox paths.
Existing custom constraints without an nginx equivalent belong in documented
toksec_* extension directives, or in the run manifest when they are grader limits.

Retain the executable interface `server --config /fixtures/nginx.conf` and add
`server --check-config /fixtures/nginx.conf`. The latter validates without binding
listeners. This is a configuration-language compatibility target, not full nginx
command-line compatibility. Errors identify file and line without printing secrets.
Unknown directives, invalid contexts and unsupported forms fail explicitly.

Initial invalid configuration exits before listening. Invalid reload retains the
previous working configuration. Before publication, define transactional behavior
for includes, root changes and listener changes. A pinned nginx build can serve as
a differential oracle for the supported subset; toksec-specific constraints must
be tested separately. Pin its build options and version in the protocol manifest.

## Stage 7 HTTPS and TLS

### Approved dependency exception

Allow one pinned system OpenSSL build for both languages. C++ links libssl and
libcrypto; Rust uses their C ABI through FFI. The sandbox supplies the library,
headers/API documentation, exact linker recipe and required runtime dependencies.
No downloaded packages, HTTP frameworks, subprocess TLS proxies or agent-written
cryptographic algorithms. Agents still implement HTTP, configuration and event
handling themselves. Record OpenSSL version, build configuration and library
hashes for reproducibility. Count its memory and CPU in server resource usage.

This is a proposed replacement for the no-crypto-library rule in Stage 7 and
above only. Build allowlists, runtime mounts and Rust linking need implementation
and tests before the profile is runnable. No TLS credentials come from the host.

### Initial HTTPS contract

- HTTP/1.1 over TLS 1.2 and TLS 1.3. Reject older TLS versions. Publish an exact
  approved cipher/group policy and fixture key types with the frozen protocol.
- Support listen ... ssl, ssl_certificate, ssl_certificate_key and
  ssl_protocols in their specified nginx contexts. Load PEM chains and keys;
  reject unreadable material and mismatched keys before accepting traffic.
- Multiple named HTTPS virtual servers share a listener. SNI selects the
  certificate. Publish default-server and unknown/absent-SNI behavior explicitly.
  Define HTTP Host routing independently, including SNI/Host mismatch behavior.
- Offer only http/1.1 through ALPN. Specify no-ALPN and no-common-protocol behavior.
  Advertising h2 without implementing HTTP/2 is a correctness failure.
- Bound handshake time, connections and memory. Slow or fragmented handshakes
  must not prevent other clients from progressing. Handle partial reads/writes
  and OpenSSL retry states without blocking the whole server or spinning.
- Preserve the stage's HTTP response and streaming semantics on encrypted
  connections. Define TLS EOF/truncation handling and bounded close behavior.
- Reload configuration and certificate material atomically. New connections use
  the new generation; established connections may complete on the old generation.
  Invalid replacement material leaves the old generation serving.
- Session resumption and TLS 1.3 early data are disabled in the initial profile.
  Add resumption only as an explicitly tested extension with separate benchmarks.

This first HTTPS stage covers client-to-server termination. Encrypted upstream
connections, mutual TLS, certificate issuance/ACME, OCSP, HTTP/2 and HTTP/3 are
outside it. A future upstream-TLS extension must require certificate-chain and
hostname verification against supplied trust roots; encryption alone is not its
acceptance condition.

Example target configuration, illustrative until the directive table is frozen:

```nginx
events {
    worker_connections 8192;
}

http {
    server {
        listen 127.0.0.1:8443 ssl;
        server_name alpha.test;
        ssl_certificate /fixtures/tls/alpha-chain.pem;
        ssl_certificate_key /fixtures/tls/alpha-key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            root /www;
            index index.html;
        }
    }
}
```

## Supplied inputs and independent grading

Keep shared tagging, last-release grading, capacity accounting and implementation
freedom. No starter server or comprehensive test suite is supplied. Supply the
complete English contract, directive table, small example configuration, test-only
certificates/keys/trust root, approved TLS API documentation and build interface.

Minimal visible checks demonstrate one valid configuration, one HTTPS GET with
certificate verification and one persistent HTTPS connection. Later stages add
one ordinary example of the new interface. Agents design their own broader tests.

Held-out tests vary inputs while exercising published requirements. Configuration
checks cover lexical boundaries, invalid contexts, inheritance, includes,
selection precedence and failed reload. TLS checks cover both protocol versions,
certificate verification and SNI selection, ALPN, malformed/fragmented handshakes,
stalls, key mismatch, certificate rotation, partial I/O and encrypted HTTP bodies.
The trusted clients must verify certificates and hostnames using the fixture CA;
disabling verification is not acceptable test evidence.

API correctness still gates all performance credit. Progress tags can earn the
existing partial correctness credit even when the complete stage is unfinished.
An incomplete HTTPS implementation does not receive plaintext-only performance
credit for a stage whose required TLS checks fail.

## Performance profile

Retain plaintext baselines and add separate encrypted workloads with 4/64 KiB
responses at 256/4096 clients. Test TLS 1.2 and 1.3 independently. Do not aggregate
them into an unexplained throughput number.

- Fresh full-handshake connections, with resumption disabled. Report complete
  verified HTTPS requests/s, handshake latency, end-to-end latency and failures.
- Persistent HTTPS connections. Report useful response throughput and latency
  separately from initial handshake establishment and warmup.
- Later stages add large transfers, proxy/cache traffic and mixed HTTP/HTTPS
  traffic with per-class metrics. Verify decrypted payload bytes in every case.

TLS clients can themselves saturate. Pin and calibrate generators separately,
record their TLS versions and cipher negotiation, and collect server/upstream
scheduler-wait evidence in addition to CPU totals. Declare warmup, request and
handshake deadlines only after calibration; do not silently extend the current
v8 two-second deadline or compare changed profiles as equivalent measurements.

At Stage 10, compare fixed 1/2/4-CPU process-tree budgets and enforce aggregate
memory/descriptor limits. Define cache/coalescing scope and global rate-limit
semantics before grading multiple workers. Report successful-request latency
alongside rejection, errors, timeouts and recovery, with no credit for rejecting
all offered work quickly.

## Original launch checklist

The experimental Stage 10 runner supplies OpenSSL builds, TLS fixtures, sandbox
execution, tagged releases, and partial checks. Complete acceptance still requires
the full configuration and lifecycle matrix and calibrated performance workloads.
The original implementation checklist was:

1. Freeze the directive/variable subset and exact nginx compatibility boundaries.
2. Define fixtures and language-neutral configuration tests, including reload.
3. Implement approved OpenSSL compilation, dependency validation and sandbox mounts.
4. Add deterministic TLS fixtures, independently verified clients and held-out cases.
5. Calibrate plaintext, handshake and persistent HTTPS workloads on reserved CPUs.
6. Publish new versioned stage packets and verify last-tag extraction/grading.

No campaign is launched by this document. Existing budget defaults are not evidence
that these larger tasks can finish within the same spend.

## Sources

- [nginx configuration structure and reload](https://nginx.org/en/docs/beginners_guide.html).
- [nginx HTTPS module, OpenSSL dependency and TLS directives](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).

These sources establish nginx behavior. The stage ordering, dependency restrictions,
evaluation profile and deferred features above are Toksec design choices.
