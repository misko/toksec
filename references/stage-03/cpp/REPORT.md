# Stage 3 C++ reference

Implemented from scratch against the http-v8 Stage 3 contract. The frozen source
passes the complete applicable host API suite and the retained focused probes.
Performance has **not** been validated. The coordinating agent will run
supplemental measurements centrally; no benchmark was launched by this builder.

## Frozen source

- Source: `references/stage-03/cpp/main.cpp`
- SHA-256: `c945d0b5c32cbffc2979aa2621533c0905142851c5e54a64883b41587845285e`
- Build interface: `g++ -std=c++20 -O3 -DNDEBUG -pthread`.
- Evaluator compiler: `g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0`.
- No third-party dependencies, subprocess delegation, paid model calls, or further
  subagents were used. All compilation, API evaluation, and focused probes were
  launched with `taskset -c 4`.

## Architecture and implemented behavior

The server uses one nonblocking, level-triggered epoll loop. Each connection has
one active response and a header staging buffer capped by `header_bytes + 1`.
Requests are materialized serially, so the response queue stays within every
positive configured `pipeline_depth`. Reads pause during output; subsequent
pipelined requests remain ordered in the bounded staging buffer or socket receive
queue. A turn sends at most 256 KiB of file payload or completes 16 buffered
responses before returning to epoll.

Regular files are sent with explicit sendfile offsets. Headers use `MSG_MORE`
when followed by a body. An LRU of 256 immutable regular-file descriptors and
metadata avoids repeated filesystem traversal for frequently requested paths;
active responses retain shared ownership when an entry is evicted. There are no
file-body buffers proportional to representation size.

The parser enforces CRLF, header names, request-line syntax, local request-body
prohibitions, exact header limits, versions, and Host validity. It accepts opaque
non-UTF-8 header values. HTTP/1.0 defaults to close; HTTP/1.1 persists unless a
case-insensitive Connection token requests close or `max_requests` is reached.
GET and HEAD share representation headers. Error bodies are empty.

Routing covers the configured default and second host, exact redirect, alias
prefix, directory slash redirects preserving the query, index files, and MIME
types. Paths undergo one strict UTF-8 percent-decoding pass. Decoded `..` is
forbidden. Component-wise openat with `O_NOFOLLOW`, followed by fstat, rejects
symlinks and nonregular objects without blocking on FIFOs. The selected host or
alias directory supplies the traversal root. Local files have stable quoted
metadata-derived ETags, weak/list conditional matching, conditional precedence,
and one closed, open-ended, or suffix bytes range, including HEAD and 416 framing.

Timers are checked at 10 ms intervals. An incomplete header has an absolute
deadline from its first received byte, including buffered partial pipeline
headers. Idle and stalled-write deadlines are separate; successful output updates
write progress. The connection cap is enforced at accept. Output interest excludes
RDHUP to avoid spinning on a half-closed stalled reader. Final responses use
SHUT_WR followed by a nonblocking bounded drain, with a maximum 250 ms linger
(clamped to the configured idle limit), preserving FIN rather than immediately
resetting a connection with unread pipelined bytes.

C++ memory ownership uses standard containers and RAII. Linux/POSIX calls are
direct; syscall return values are checked. There is no custom allocator or
unchecked application buffer indexing. sockaddr casts are confined to constructing
the validated IPv4/IPv6 listen address.

## API evidence

The full CLI was run independently for each retained source revision:

```sh
taskset -c 4 python3 evaluate.py --section api --level 3 --language cpp \
  --source references/stage-03/cpp/main.cpp \
  --output .runs/references/stage-03-cpp/api-004
```

The final result is `.runs/references/stage-03-cpp/api-004/result.json`: build
passed, **26/26 API checks passed**, no compiler diagnostics, no server diagnostics,
and no observed server exit during checks. This includes configuration rejection,
connection capacity, absolute header deadlines, stalled-write slot recovery, and
pipeline backpressure as well as inherited static/persistent and routing cases.

Earlier complete API results and source snapshots remain retained:

| Result path under `.runs/references/stage-03-cpp/` | Result | Source SHA-256 |
| --- | --- | --- |
| `api-001/result.json` | 26/26 passed | `da300ad8cc73c2ce37fe9d5c5ec477c0488307a034eb62cad074050fd1e7671b` |
| `api-002/result.json` | 26/26 passed | `41b5dea6aab139ce478f8609aae95f51f70f4a14dba39b7cb191acba52993626` |
| `api-003/result.json` | 26/26 passed | `ab0c3340fb518f831ba7a1eb2164efa8a10a7ec8a5e9d94152bb14ade2442c0c` |
| `api-004/result.json` | 26/26 passed | `c945d0b5c32cbffc2979aa2621533c0905142851c5e54a64883b41587845285e` |

Each `api-NNN/candidate/` contains the evaluated source, executable, and build
record. The later revisions added graceful final close, half-close behavior,
pipeline deadline coverage, large-limit arithmetic, case-insensitive range units,
and header/body coalescing. These are implementation changes, not measured
performance improvements.

## Additional correctness evidence

The final focused suite is
`.runs/references/stage-03-cpp/focused-003/probe.py`; results are
`.runs/references/stage-03-cpp/focused-003/result.json`. All **16 scenarios** passed
against the frozen source hash. The exact invocation was:

```sh
taskset -c 4 python3 .runs/references/stage-03-cpp/focused-003/probe.py \
  .runs/references/stage-03-cpp/api-004/candidate \
  > .runs/references/stage-03-cpp/focused-003/result.json
```

Four successful-server scenarios cover:

- Host grammar and decimal ports, HTTP/1.0 host selection, valid UTF-8 paths,
  invalid/overlong/surrogate UTF-8, one-pass decoding, nested symlinks, FIFO
  traversal, missing indexes, and query-preserving redirects.
- Weak/list ETags and conditional precedence over malformed ranges; upper-case
  range units, huge numbers, empty files, zero suffixes, reversed bounds, malformed
  and duplicated ranges, and body-free HEAD errors/ranges.
- Malformed pipeline ordering; the final advertised close after 100 responses
  while 1,900 additional requests remain unread; half-closed pipelines and a
  complete 2 MiB transfer; fairness with a half-closed stalled large-file reader.
- Changed default host and roots, `max_requests=7`, `pipeline_depth=2`,
  `header_bytes=512`, a 250 ms header deadline, a 250 ms write deadline with
  `max_connections=1`, and the maximum positive uint64 header limit.

Twelve additional scenarios independently reject malformed listen addresses and
ports, numeric overflow/negative/nonnumeric limits, invalid default hosts, missing
or relative mapped roots, an empty redirect destination, and an unsafe index name.

Earlier focused results are retained at `focused-001/result.json` and
`focused-002/result.json`; both passed against their recorded source snapshots.

## Measurement status and limits

No throughput, p50/p95/p99, error/timeout rate, CPU, RSS, round spread, or generator
eligibility measurement has been collected by this builder. Neither the declared
five-round matrix nor a performance comparison is claimed complete. Full-matrix
measurements, including both 256- and 4096-client workloads, remain the
coordinator's work after source freeze.

Finite API and focused tests establish the behavior exercised above; they do not
prove complete correctness or optimal performance. File metadata caching relies
on the contract's immutable local files. Deadline precision is limited to the
10 ms timer sweep. Active transfers can retain evicted descriptors until their
response completes; extreme simultaneous distinct-file transfers can approach
the process descriptor limit. No source changes are planned after the frozen
hash above without a new API gate and separately recorded evidence.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 10/12 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-03-cpp/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
