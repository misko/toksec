import hashlib
import json
from dataclasses import asdict
from stages.common.performance import Workload, matrix
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'rust-http-v6'
TITLES = {1: 'Static files', 2: 'Concurrent persistent HTTP', 3: 'Hosts and routing',
          4: 'Reverse proxy', 5: 'TLS and operational features'}
DESIGN = {
    1: 'Begin with a blocking, bounded request reader and exact file response. Submit that runnable path early. Add strict parsing and confinement before optimizing. Consider bounded workers or nonblocking sockets only after the contract passes. Avoid allocating the whole file per connection; immutable file metadata and sendfile are permitted.',
    2: 'Model each connection with explicit read-header, write-header, write-body and idle states. At 4096 clients a thread and a large buffer per connection can exceed the memory limit. Consider nonblocking sockets with epoll/poll and small bounded buffers. Track deadlines independently and preserve pipeline order under partial writes.',
    3: 'Normalize and validate the path once, then select host and route before opening a confined file. Keep conditional requests, ranges and HEAD as transformations of one representation descriptor. Avoid divergent GET/HEAD paths and validate alias confinement separately.',
    4: 'Model downstream and upstream lifecycles separately. Bound request and response bodies, make retry eligibility explicit, and return failed connections to no pool. First prove byte-exact proxying, then add healthy connection reuse and nonblocking backpressure.',
    5: 'Get maintained-library TLS working before adding caching, compression and reload. Account for OpenSSL WANT_READ/WANT_WRITE states. Treat configuration as an immutable snapshot replaced after full validation. Give cache keys and byte accounting explicit types. Exercise cache isolation and shutdown before optimizing.',
}
BASE_CONFIG = {'listen': '127.0.0.1:8080', 'root': '/www', 'max_connections': '8192',
               'header_bytes': '8192', 'header_timeout_ms': '1000', 'idle_timeout_ms': '2000',
               'write_timeout_ms': '2000', 'max_requests': '100', 'pipeline_depth': '16'}
EXTRA_CONFIG = {
    3: {'default_host': 'alpha.test', 'host_root': 'beta.test:/www/beta',
        'alias': '/assets/:/www/assets/', 'redirect': '/old:/hello.txt', 'index': 'index.html'},
    4: {'proxy_prefix': '/proxy/', 'upstreams': '127.0.0.1:8081,127.0.0.1:8082',
        'upstream_timeout_ms': '500', 'body_bytes': '1048576'},
    5: {'tls_listen': '127.0.0.1:8443', 'tls_cert': '/fixtures/cert.pem',
        'tls_key': '/fixtures/key.pem', 'cache_ttl_ms': '1000', 'cache_bytes': '4194304',
        'gzip': 'true', 'rate_per_second': '0', 'rate_burst': '2', 'drain_timeout_ms': '2000'},
}
API = {
    3: (
        'Require exactly one valid Host on HTTP/1.1 requests; missing, duplicate or unknown hosts return 400. HTTP/1.0 without Host uses default_host.\n'
        'Match Host case-insensitively after removing an optional decimal port. default_host uses root; host_root maps beta.test to its own root.\n'
        'Match the exact redirect path before file routing and return 302 with Location. alias maps its path prefix to the configured filesystem prefix; enforce confinement within that prefix.\n'
        'For a directory with a trailing slash serve index if it is a regular file. A directory without a trailing slash returns 301 to its slash form, preserving the query. A directory without index returns 403.\n'
        'Map .html to text/html, .txt to text/plain, and other files to application/octet-stream.\n'
        "Emit a stable quoted ETag on local 200 responses. Matching If-None-Match or '*' returns 304 with no body, Content-Length: 0 and the ETag. Conditional matching precedes Range.\n"
        'Support one bytes range on GET/HEAD: N-M, N-, and -N. Clamp M to EOF. Satisfiable ranges return 206, exact bytes and Content-Range: bytes N-M/SIZE. Unsatisfiable ranges return 416 and Content-Range: bytes */SIZE. Malformed or multiple ranges return 400.\n'
        'Range and conditional behavior applies to the selected host, alias and index representation. A HEAD response has no body even for a range or error.\n'
    ),
    4: (
        "For paths beneath proxy_prefix, strip the prefix and send an origin-form '/' plus the remainder to the upstream, preserving the query. Local routes retain their Level 3 semantics.\n"
        'Proxy GET, HEAD and POST. Permit a single valid Content-Length body or Transfer-Encoding: chunked, but never both. Reject duplicate lengths, unsupported transfer codings and invalid chunk syntax with 400. Decoded bodies above body_bytes return 413. Decode chunks and optional bounded trailers; do not forward trailers.\n'
        'Use round-robin upstream selection for consecutive healthy requests. Reuse healthy HTTP/1.1 upstream connections. Strip hop-by-hop headers and every header named by Connection in both directions. Rewrite Host to the selected upstream authority.\n'
        'Forward end-to-end headers, status and exact decoded body. Upstream Content-Length and chunked bodies are supported. Emit a known Content-Length downstream; bound response bodies to body_bytes, returning 502 if exceeded. HEAD has no downstream body.\n'
        'Reject ambiguous or malformed upstream framing with 502. Apply upstream_timeout_ms to connection and response completion. A GET/HEAD may retry once on the next upstream only before a downstream response begins. Never retry POST. Final transport/malformed failures return 502; final deadline expiry returns 504.\n'
        'Keep downstream request/response order. Upstream failures and disconnected downstream clients must not leak unbounded connections or poison subsequent requests.\n'
    ),
    5: (
        'Serve the same API over HTTP and TLS on tls_listen, using the supplied PEM certificate and key and a maintained TLS library. Support TLS 1.2 or newer. SNI alpha.test and beta.test select the same certificate; Host still selects routing. Do not implement cryptography yourself.\n'
        'Cache successful proxy GET responses with explicit Cache-Control: public,max-age=N, capped by cache_ttl_ms. Cache key includes scheme, host, path and query. Honor Vary: Accept-Encoding. Vary:* and any other Vary field bypass cache. Requests with Authorization and responses with Set-Cookie, private or no-store bypass cache.\n'
        "Keep total cached body bytes within cache_bytes and evict entries when necessary. HEAD may use an existing GET entry but must not create an empty GET entry. Expired entries are fetched again; conditional cache revalidation is outside this level's profile.\n"
        'If gzip=true and Accept-Encoding permits gzip with nonzero quality, gzip local text representations at least 1024 bytes. Include Content-Encoding: gzip and Vary: Accept-Encoding; Content-Length is the compressed size. HEAD uses the same representation headers. Range responses remain uncompressed. Use zlib or an equivalent approved compression library.\n'
        'When rate_per_second > 0, enforce a global token bucket shared by HTTP and TLS, refilled by monotonic time up to rate_burst. Rejected requests receive 429 and Retry-After. Benchmarks disable this limiter.\n'
        'On SIGHUP reread the entire configuration atomically. An invalid reload retains the previous configuration. A valid reload changes roots, routing, cache and limiter settings for subsequent requests; flush cache. Listener addresses and TLS paths are immutable across reload and changes to them invalidate reload.\n'
        'On SIGTERM stop accepting new connections, finish in-flight responses up to drain_timeout_ms, then exit. TLS and plain listeners both drain. Rate limiting, caching and reload must not break path confinement or HTTP framing.\n'
    ),
}



def configuration(level):
    if level not in TITLES:
        raise ValueError('level must be 1 through 5')
    values = dict(BASE_CONFIG)
    for minimum, extra in EXTRA_CONFIG.items():
        if level >= minimum:
            values.update(extra)
    return values


def workloads(level):
    configuration(level)
    if level == 1:
        from stages.stage1.performance import workloads as selected
        return selected()
    if level == 2:
        from stages.stage2.performance import workloads as selected
        return selected()
    modes = [('fresh', False, False, False, '/data/'), ('persistent', True, False, False, '/data/')]
    if level >= 4:
        modes.append(('proxy', True, False, False, '/proxy/data/'))
    if level >= 5:
        modes.extend([('tls', True, True, False, '/data/'), ('gzip', True, False, True, '/text/')])
    return matrix(modes)


def specification(level):
    from toksec.checks import cases_for, configured_cases, EXTERNAL_CASES
    configuration(level)
    return {'version': VERSION, 'level': level, 'title': TITLES[level],
            'configuration': configuration(level), 'requirements': [(ROOT / 'stages/common/HTTP.md').read_text(), (ROOT / f'stages/stage{min(level, 2)}/SPEC.md').read_text()] + [API[n] for n in range(3, level + 1)],
            'cases': [{'id': c.id, 'description': c.description} for c in cases_for(level) + configured_cases(level) + EXTERNAL_CASES],
            'benchmarks': [asdict(w) for w in workloads(level)],
            'build': {'compiler': 'rustc', 'edition': '2021', 'optimization': 3, 'source': 'main.rs',
                      'approved_libraries': ['libc'] + (['libssl.so.3', 'libcrypto.so.3', 'libz.so.1'] if level == 5 else [])},
            'resources': {'server_cpu_cores': 1, 'server_address_space_mib': 512, 'server_open_files': 16384,
                          'compile_address_space_mib': 4096, 'compile_cpu_seconds': 60, 'compile_wall_seconds': 120}}


def instruction_files(level):
    configuration(level)
    return ['RULES.md', 'stages/common/INTERFACE.md', 'stages/common/HTTP.md',
            f'stages/stage{min(level, 2)}/SPEC.md', 'stages/common/BENCHMARK.md']


def packet(level):
    spec = specification(level)
    lines = [f'# Stage {level}: {TITLES[level]}', '', f'Contract version: {VERSION}.', '']
    for name in instruction_files(level):
        lines.extend([(ROOT / name).read_text(), ''])
    lines.extend(API[n] for n in range(3, level + 1))
    from stages.common.smoke import cases as smoke_cases
    visible = [{'id': c.id, 'description': c.description} for c in smoke_cases(level)] if level <= 2 else spec['cases']
    lines.extend(['## Required configuration', '', '```ini',
                  *[f'{k}={v}' for k, v in spec['configuration'].items()], '```', '',
                  '## Supplied smoke checks', '',
                  'These checks demonstrate ordinary API usage only. Design your own tests from the English requirements. Full independent grading is withheld until the run ends.', ''])
    lines.extend(f'- `{c["id"]}`: {c["description"]}' for c in visible)
    lines.extend(['', '## Workload matrix', '', '| Workload | Clients | Bytes | Connection |', '|---|---:|---:|---|'])
    lines.extend(f'| {w.id} | {w.clients} | {w.size} | {"persistent" if w.persistent else "fresh"} |' for w in workloads(level))
    lines.append('')
    return '\n'.join(lines)


def fingerprint():
    paths = list((ROOT / 'toksec').glob('*.py'))
    paths += [ROOT / name for name in ('controller.py', 'evaluator.py', 'evaluate.py', 'metering.py', 'runner.py', 'RULES.md')]
    paths += [p for p in (ROOT / 'stages').rglob('*') if p.suffix in ('.py', '.md')]
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in sorted(paths))).hexdigest()


def publish(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for level in TITLES:
        (directory / f'level-{level}.md').write_text(packet(level))
        (directory / f'level-{level}.json').write_text(json.dumps(specification(level), indent=2) + '\n')
