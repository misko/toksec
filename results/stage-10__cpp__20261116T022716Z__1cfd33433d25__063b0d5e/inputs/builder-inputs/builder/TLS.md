# Stage 10 HTTPS contract

Status: proposed builder reference. Runtime dependency packaging and independent verification remain publication gates.
All HTTP.md requirements apply to decrypted HTTP/1.1 traffic. HTTPS uses the same routing, cache, limiter, and worker budget as plaintext.

## Approved dependency

The sandbox supplies one pinned OpenSSL build, including libssl, libcrypto, headers, API documentation, and runtime dependencies.
C++ links that build directly. Rust calls the same C ABI through source-defined FFI declarations.
The publication manifest must record the exact version, build options, hashes, and compiler/linker recipes for both languages.
Those values are not frozen in this draft. A host's incidental OpenSSL installation does not satisfy this requirement.
Downloaded crates, other crypto libraries, HTTP frameworks, subprocess TLS proxies, and handwritten cryptography are excluded.
OpenSSL memory, CPU, and descriptors count toward the aggregate process-tree limits in INTERFACE.md.

## Directives and fixtures

| Directive and complete argument form | Context | Default and inheritance |
|---|---|---|
| `ssl_certificate PATH` | http, server | No default. Inherits from http if absent in server. One PEM chain file. |
| `ssl_certificate_key PATH` | http, server | No default. Inherits from http if absent in server. One unencrypted PEM private key. |
| `ssl_protocols TLSv1.2 TLSv1.3` | http, server | Both versions. This is the only accepted argument sequence. Inherits if absent. |

Each occurs at most once in its context. Paths follow CONFIGURATION.md and contain no variables.
Every server on an `ssl` endpoint requires an effective certificate and key pair.
Validation rejects unreadable or malformed PEM, an empty chain, a mismatched key, and keys other than RSA-2048.
The leaf is first in the chain. Any intermediates follow in issuer order. The trust root need not be sent.
The fixture packet supplies a test CA and two independently verifiable chains with DNS SANs `alpha.test` and `beta.test`, respectively.
Each certificate has exactly its corresponding DNS SAN. Common Name fallback is not an acceptance condition.
Fixtures also supply replacement RSA-2048 chains with the same names and different serial numbers for reload checks.
Fixture certificates are valid throughout the declared test clock interval. Fixture private keys are test-only inputs.
Clients verify the fixture CA, validity interval, chain, and expected hostname. Disabling verification cannot demonstrate success.
The sample listener is `127.0.0.1:8443`; plaintext uses `127.0.0.1:8080`.

## Protocol policy

TLS 1.2 and TLS 1.3 are both required. Older versions fail the handshake.
TLS 1.2 permits only `ECDHE-RSA-AES128-GCM-SHA256` and `ECDHE-RSA-AES256-GCM-SHA384`.
TLS 1.3 permits only `TLS_AES_128_GCM_SHA256` and `TLS_AES_256_GCM_SHA384`.
Supported key-exchange groups are X25519 and secp256r1. Either common permitted cipher and group may be selected.
The OpenSSL provider's supported RSA-PSS and RSA-PKCS1 SHA-256 or SHA-384 signature schemes may be used where the negotiated TLS version permits them.
No session IDs, session tickets, or PSK session resumption are accepted. TLS 1.3 ticket issuance and early data are disabled.
Clients receive a full handshake on every new connection. TLS renegotiation and client authentication are disabled.
The only selectable ALPN protocol is `http/1.1`. A client offering it negotiates it even when the same list also contains `h2`.
A client without ALPN may exchange HTTP/1.1. A nonempty ALPN list without `http/1.1` fails with `no_application_protocol`.
There is no HTTP/2 fallback or advertisement.

## SNI and HTTP routing

An ASCII DNS SNI name matches server_name case-insensitively among servers on the accepted listener.
Absent or unknown SNI uses the endpoint default server's certificate. Malformed TLS or malformed SNI encoding fails the handshake.
The SNI name does not rewrite or constrain the later Host field.
For example, SNI `alpha.test` plus Host `beta.test` presents alpha's certificate and serves beta's HTTP route.
The client must verify alpha's identity in that example. HTTP/1.1 Host validation still rejects missing, duplicate, or unknown Host.
Certificate selection does not leak across connections, workers, or reload generations.
The same protocol policy applies to every server on a listener, including the default.

## Nonblocking I/O and reload

Fragmented ClientHello records, partial TLS reads and writes, and OpenSSL WANT_READ or WANT_WRITE states must make progress without blocking other clients.
Readiness registration follows the operation OpenSSL requests, even when a write requires reading or a read requires writing.
There is no busy polling while a peer is stalled. Handshakes count against downstream admission and per-worker connection limits.
The absolute handshake timer starts at accept. Expiry closes the connection without an HTTP response.
HTTP deadlines begin at their specified HTTP events after handshake completion. The HTTP response framing must match the decrypted bytes.
A peer close_notify terminates TLS input. A transport EOF without close_notify is an unclean close.
Incomplete HTTP input is never accepted as a complete request or body because the TLS transport closed.
After either input close, complete accepted work may finish only if writes remain possible and its existing deadlines permit it.
An unclean close does not invalidate an already complete, correctly framed response seen by the client.
On local close, attempt close_notify without blocking. Do not wait more than 1 second or beyond the remaining drain deadline.
Close transport and release all connection state when the bound expires.

SIGHUP loads fresh certificate bytes even when certificate paths are unchanged.
The master validates the whole candidate before commit. Invalid keys or certificates retain the previous complete generation.
New accepts after commit use the new certificate. Already accepted connections retain their captured TLS generation, including incomplete handshakes.
Existing TLS connections retain both their TLS and routing generations, bounded by the old generation's drain deadline.
Certificate contexts remain alive until their connections finish. Worker replacement uses the currently committed generation.

Encrypted upstreams, mutual TLS, ACME, OCSP, custom cipher directives, HTTP/2, and HTTP/3 are outside this profile.
The native TLS directive subset is based on the nginx [HTTPS module reference](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).
The fixed algorithms, ALPN behavior, resumption policy, and closure bounds above are explicit Toksec profile choices.
