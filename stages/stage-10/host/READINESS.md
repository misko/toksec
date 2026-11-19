# Stage 10 launch gates

This host-only plan is not part of the builder's input allowlist. The Stage 10
packet is a reviewable draft. It is not supported by evaluate.py or the controller.

| Gate | Current state | Required evidence |
|---|---|---|
| Instruction/input separation | Packet prepared | Enumerated hashed allowlist, no host tests/reference source/CA signing key |
| Exact contract | Draft | Resolved directive table, cache limits, global queues, resource accounting and sustained-test tolerances |
| Stage registry/publisher | Not implemented | Versioned Stage 10 packet, inherited contracts, no v8 fingerprint changes |
| OpenSSL build policy | Not implemented | C++ and Rust link in build sandbox; reject other dependencies |
| Runtime TLS fixtures | Sample certificates prepared | Sandboxed SNI/rotation/client-verification tests on varying fixtures |
| Aggregate isolation | Not implemented | Enforced 512 MiB tree limit, total 16,384 FDs, 1/2/4-CPU sets and scratch limit |
| Multiworker accounting | Not implemented | Include master/live/exited workers, correct worker-kill cleanup, no child-process rejection |
| Visible tools and releases | Not implemented for Stage 10 | Plain bootstrap tag before TLS completion; reject regressions; grade last completed tag after interruption |
| Full API suite | Not implemented | Independent cases for every published obligation and injected faults |
| TLS/streaming load driver | Not implemented | Verified bytes/certificates, phase-specific failures, separate fresh/persistent workload identities |
| Calibration | Not performed | Reserved CPUs, generator/upstream headroom and stall traces, frozen durations/matrix |
| End-to-end dry run | Not performed | Rebuild/extract/grade a tagged fixture candidate without model spend |

Do not set launch_ready true while any required gate is missing. A source file
named stage10 or a packet with smoke descriptions does not satisfy these gates.

Observed current incompatibilities include levels restricted to 1–5 in
toksec/specification.py and languages.py; old key=value fixtures; denied
libssl/libcrypto/OpenSSL headers; per-process rlimits and single-CPU selection;
and benchmark.py's rejection of child processes and single-PID CPU/RSS sampling.
Removing the child-process rejection without replacing accounting would hide work.
Sampling aggregate FDs is not enforcement of a hard aggregate descriptor cap.

Implement the next protocol in a separately versioned checkout/profile so frozen
v8 comparisons remain reproducible. Port shared rules by generation with explicit
source hashes. The RULES.md copy here is a review snapshot, not a second authority
to maintain independently. Before a real run regenerate it from shared rules plus
the Stage 10 metadata and record both identities.

## Hidden cases and public obligations

Keep checker source, input variants, fault schedules and scoring code host-only.
Publish every behavior and measurement rule. Cover malformed configuration,
context/inheritance/include boundaries, unsupported directives, SNI/Host/ALPN,
TLS versions, invalid keys and failed certificate reload, streaming truncation,
queue cancellation/retry fairness, cache variants/revalidation/coalescing,
global limits across workers, worker replacement and shutdown/reload races.

Use a pinned nginx binary as a compatibility oracle only for the supported native
directive subset. Toksec extensions and intentionally narrower HTTP behavior need
independent assertions. Nginx is not installed in the inspected preparation
environment; the example configurations have not been checked with nginx -t.

## First-tag fixture

Run bootstrap with fixtures/config/bootstrap.conf, which uses only events, http,
server, listen, server_name, location and root. Do not require parsing TLS/cache/multiworker directives
before the first plaintext release can be published. Later smoke checks use the
full example. All final checks use independently generated configurations.

## Budget and packaging

No campaign is created or launched here. A run's dollar/token/wall budget must be
explicitly selected and enforced by its chosen backend. Native subagents are not
metered API campaigns or independent sandbox builders. Supply only the selected
language policy, not both. Pin the OpenSSL ABI and API documentation alongside
the executable libraries before launch. This preparation packet records the
observed local version but does not certify a deployable runtime image.
