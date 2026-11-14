# Stage 2 C++ reference

Status: implemented and API-validated. Performance has not been measured by this
agent; the coordinating agent will run supplemental measurements centrally.

Final source: `references/stage-02/cpp/main.cpp`.
SHA-256: `42b77d37b1309cd51fb48b2dad3af9066a2ce6c55925a8be1899231272879ea3`.

## Implementation

The server is an independently written C++20 executable using the standard
library and Linux/POSIX APIs. One nonblocking epoll loop manages connections.
Each connection holds one bounded header accumulator and one active response.
Reads peek ahead and consume exactly one complete header, leaving later pipeline
bytes in the kernel while output is blocked. The application therefore keeps at
most one in-flight response, within every positive configured `pipeline_depth`.
Legal longer pipelines are consumed in order rather than rejected. Event work is
bounded by request/read counts and a 256 KiB write budget to maintain fairness.

The parser validates request-line spacing, method/header tokens, HTTP versions,
CRLF framing, NUL exclusion, forbidden local bodies, duplicate Content-Length,
transfer coding, and the configured header byte limit. Header values are opaque
bytes. Connection close tokens are case-insensitive. GET and HEAD share status
and representation selection. HTTP/1.0 closes; HTTP/1.1 persists until requested
close, `max_requests`, an error requiring close, or a deadline.

Paths are percent-decoded once, validated as UTF-8, and checked for forbidden
components. File access walks directory descriptors with `openat` and
`O_NOFOLLOW`, checks the final object with `fstat`, and never follows symlinks
below the configured root. Nonblocking open avoids FIFO-open stalls.

A bounded 128-entry cache shares immutable file metadata and contents up to
64 KiB. Larger files use `sendfile` with a separate offset for each response.
Eviction closes descriptors and frees buffered contents even when a response
still references its metadata; that response securely reopens the file for its
next transfer. Consequently active responses do not pin an unbounded number of
cached descriptors or cached content buffers. File bytes held by the shared
cache are bounded at 8 MiB.

Header deadlines are absolute from the first consumed byte. Idle and no-progress
write deadlines are independent. Deadlines are checked during servicing and by
an expiration scan with a maximum 10 ms polling interval, shortened for smaller
configured timeouts. A blocked response does not subscribe to RDHUP events,
avoiding repeated readiness notifications from a half-closed reader. Intended
final closes shut down output and drain already queued input with bounded work,
so excess pipeline data does not cause an immediate reset after the final
response. Draining also has a deadline.

There are no third-party libraries, runtime library loading, cryptography, or
subprocess calls. C++ has no separate unsafe/FFI declaration; the OS interfaces
use raw pointers to locally owned buffers and structures, with explicit lengths.
All I/O, descriptors, and connection state are managed in one thread.

## Correctness evidence

All compilation, API evaluation, focused probes, and compiler diagnostics were
pinned with `taskset -c 2`. The final full API command was:

```sh
taskset -c 2 python3 evaluate.py --section api --level 2 --language cpp \
  --source references/stage-02/cpp/main.cpp \
  --output .runs/references/stage-02-cpp/api-003
```

| Evidence | Source SHA-256 | Result |
|---|---|---|
| `.runs/references/stage-02-cpp/api-001/result.json` | `2b505a039754a0264d8a1acd60d5de52b4ae14f0e892521d026fb590e0012873` | 21/21 required API checks passed |
| `.runs/references/stage-02-cpp/probes-001/result.json` | Initial API source above | 4/5 focused probes passed; excess pipeline after max_requests produced TCP reset |
| `.runs/references/stage-02-cpp/api-002/result.json` | `04efcea3dde6a9cb86fbd2672e8f20224a98017cd689cc4a09e607ae76186088` | 21/21 required API checks passed after close/cache/backpressure fixes |
| `.runs/references/stage-02-cpp/probes-002/result.json` | API-002 source above | 6/6 focused probes passed |
| `.runs/references/stage-02-cpp/probes-003/result.json` | API-002 source above | 51/51 expanded focused/configuration probes passed |
| `.runs/references/stage-02-cpp/api-003/result.json` | Final source above | 21/21 required API checks passed after deadline checks were strengthened |
| `.runs/references/stage-02-cpp/probes-004/result.json` | Final source above | 51/51 expanded focused/configuration probes passed |

The final evaluator compiled with g++ 15.2.0 using the prescribed C++20/O3 build,
passed its header/dependency policy, and reported no compiler or server
diagnostics. A separate `-Wall -Wextra -Wconversion -fsyntax-only` pass also
completed with no diagnostics.

The retained independent test driver is
`references/stage-02/cpp/contract_probes.py`. Its eight behavioral groups cover
excess pipelines after a three-response limit; half-close with an 8 MiB GET,
HEAD, and following GET; a 128-byte exact header boundary and malformed framing;
one-pass/invalid UTF-8 paths and symlink parents; a 250 ms persistent header
deadline; malformed targets on unknown methods; ordered output before a
malformed pipelined request; and cache churn during a blocked large response.
Another 43 cases check duplicate/unknown keys, relative roots, invalid listen
addresses/ports, and zero, signed, fractional, or overflowing values for every
numeric limit. Each invalid configuration exited nonzero within two seconds.
The cache-churn fixture files are created before clients use them and remain
immutable throughout requests.

## Performance and limitations

No benchmark was run by this agent, per the coordinator's instruction to reserve
benchmark resources for central measurements. There is no measured throughput,
latency, CPU, RSS, round spread, or eligibility claim for either client count.
The architecture alone is not performance evidence. No before/after performance
comparison was attempted.

The final source is frozen at the hash above. Full API success and the focused
probes establish the recorded finite behaviors; they do not prove exhaustive
correctness, resource bounds for every possible configuration, or maximum
performance. No known functional failure remains in the tested final source.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 5/8 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-02-cpp/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
