# Stage 1 C++ reference

Status: implemented and API-validated. The full declared performance matrix ran,
but every round was marked generator-saturated and ineligible. Performance is
therefore inconclusive, and the observed failures remain part of the evidence.

Final `main.cpp` SHA-256:
`9214aaf0ee5ef0df2c59f6b4d1b73444d72e6737b2ef51c4299ad77900e76336`.

The source was implemented from scratch for this assignment. No paid model API
calls, subprocess delegation by the server, external libraries, harness changes,
or edits outside the assigned reference/evaluation directories were made.

## Architecture and contract coverage

The server uses one nonblocking Linux `epoll` loop. It accepts at most 256 sockets
per dispatch, stores connection state by descriptor, rejects events for an old
descriptor generation, and limits active connections to `max_connections`.
Admission pauses when that limit is reached. A removable minimum heap contains
one absolute deadline per live connection; it does not accumulate obsolete timer
entries. Header deadlines start at `accept4` and never extend when bytes arrive.
The configured write timeout applies while a response is blocked and resets after
output progress. Slow request and response clients do not block other sockets.
`idle_timeout_ms`, `max_requests`, and `pipeline_depth` are required and validated;
Stage 1 always sends one response and closes, so persistent-session behavior does
not use those settings.

Request scanning validates CRLF incrementally across fragments, rejects NUL and
bare line endings, and counts the terminating CRLFCRLF against `header_bytes`.
Parsing validates methods, versions, header tokens and values, rejects folded
fields, rejects transfer coding and duplicate/nonzero/invalid content lengths,
and accepts arbitrarily many decimal zeroes within the header limit. Missing
Host is accepted. Successful and error responses include Content-Length and
Connection: close; unsupported valid methods return 405.

Path handling strips the query, decodes percent escapes exactly once, validates
UTF-8 including overlong/surrogate/range exclusions, rejects raw fragments,
absolute-form targets, NUL, backslash, and decoded `..` components. Files are
opened beneath an already-open root using component-wise `openat`, `O_NOFOLLOW`,
`O_DIRECTORY` for intermediate components, and `fstat` for final regular-file
validation. `O_NONBLOCK` prevents opening a FIFO from blocking the loop.
Directories, symlinks, FIFOs, and sockets are forbidden.

Immutable successful file responses are cached for up to 128 paths. Responses
with bodies at most 128 KiB can be buffered with their headers, within an 8 MiB
aggregate buffer budget. Larger or uncached bodies use nonblocking `sendfile`
with per-connection offsets. Cache entries hold file descriptors only when
sendfile needs them. Connection input memory grows only with that connection's
configured header limit; no file body is copied into each connection's state.

C++ has no Rust-style unsafe marker. The implementation calls POSIX/Linux socket,
file, timer, and epoll APIs directly and manages descriptors explicitly. It uses
standard-library strings and containers for buffers. It does not use pointer
arithmetic outside buffer/socket API arguments, custom allocation, runtime
library loading, cryptography, or third-party dependencies.

## Correctness evidence

All commands were run from the repository root. Compilation and API evaluations
were pinned to CPU 0 with `taskset -c 0`.

| Evaluation | Source SHA-256 | Result |
| --- | --- | --- |
| `.runs/references/stage-01-cpp/api-001/result.json` | `02e8439d002504fc9a96b83f737904c36f6206e66422aa8ca4f2be5b71872342` | Build accepted, 12/12 full host API checks |
| `.runs/references/stage-01-cpp/api-002/result.json` | `9214aaf0ee5ef0df2c59f6b4d1b73444d72e6737b2ef51c4299ad77900e76336` | Build accepted, 12/12 full host API checks |
| `.runs/references/stage-01-cpp/performance-001/result.json` | same final hash | Fresh build accepted, 12/12 full host API gate repeated before measurement |

The first accepted source is retained in `api-001/candidate/main.cpp`. Review
then removed EPOLLRDHUP subscription during blocked writes: a peer that
half-closed its request could otherwise repeatedly wake the loop while refusing
response bytes. The final source subscribes to RDHUP only while reading.
`api-002` validated that correction, and the source remained frozen throughout
the performance matrix. The exact measured snapshot is
`.runs/references/stage-01-cpp/performance-001/candidate/main.cpp`.

The full host suite covers bootstrap, binary/empty/2 MiB files, missing files,
query/percent handling, confinement, bytewise fragmentation, syntax, framing,
8192/8193-byte headers, absolute header deadline, disconnect recovery, headerless
HTTP/1.0, and seven invalid configuration variants. Both API runs and the
performance gate passed every selected check with no server diagnostics.

Additional retained test program: `references/stage-01/cpp/focused_tests.py`.
Its result is `.runs/references/stage-01-cpp/focused-001/result.json`: 47 checks
passed against the final binary. It adds:

- Literal and percent-encoded UTF-8; invalid overlong sequences, surrogates,
  values above U+10FFFF and truncated sequences; exactly-once decoding; encoded
  slash and normalized dot/repeated-slash paths; ignored query escapes.
- Intermediate-directory symlinks, final symlinks, FIFO and Unix socket rejection.
- Mixed-case framing fields, duplicate lengths, empty transfer coding, forbidden
  header-name/value bytes, nonstandard valid methods, and 400-zero lengths.
- A custom 512/513-byte header boundary, nondefault 250 ms silent and trickling
  header deadlines, and 48 silent clients isolated from an ordinary request.
- A half-closed client that does not read a 16 MiB response, isolated ordinary
  service, expiration of the custom 350 ms write deadline, and 300 fresh valid
  requests after malformed clients and timeouts.
- Invalid numeric ranges/signs/format, a zero deadline, relative root, and integer
  overflow in configuration.

These independent local diagnostics supplement the finite host suite; neither
suite proves all possible behavior.

## Full performance evidence

Command:

```sh
taskset -c 10-15 python3 evaluate.py --section performance --level 1 --language cpp --source references/stage-01/cpp/main.cpp --output .runs/references/stage-01-cpp/performance-001
```

The parent assigned these CPUs exclusively among this reference team's benchmark
runs. The server used CPU 10 and four trusted generators used CPUs 11–14.
Independent preexisting host activity was subsequently observed on benchmark
CPUs; affinity alone did not reserve the machine. Each workload ran the declared
five rounds, one-second warmup, three-second measurement and two-second client
deadline. Exit status was 3 because the measurement eligibility checks failed.
No validity threshold was changed and no invalid result was promoted.

Raw evidence:
`.runs/references/stage-01-cpp/performance-001/result.json` and
`.runs/references/stage-01-cpp/performance-001.console.log`.
Framework fingerprint:
`6fb7772770821e4f56dbcebe476c5cf9647b02c65faa6c0e5433d0cd355ebcb4`.

The figures below are descriptive observations from **ineligible** rounds.
Latency columns are medians of the five round-level p50/p95/p99 values, not a
merged histogram. Spread is the minimum to maximum observed round goodput.

| Bytes / clients | Median req/s | Round req/s range | Payload MiB/s | p50 / p95 / p99 ms | Worst round p99 ms | Failures / timeouts | Eligible rounds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4096 / 256 | 28,537.3 | 23,728.3–39,026.7 | 111.47 | 6.7 / 16.4 / 30.9 | 46.1 | 0 / 0 | 0/5 |
| 65536 / 256 | 9,126.3 | 6,864.0–11,283.0 | 570.40 | 17.6 / 47.3 / 84.6 | 131.1 | 22 / 22 | 0/5 |
| 4096 / 4096 | 12,051.7 | 10,573.0–15,332.3 | 47.08 | 221.8 / 482.1 / 558.2 | 598.2 | 720 / 0 | 0/5 |
| 65536 / 4096 | 9,485.7 | 7,692.3–10,207.3 | 592.85 | 328.6 / 635.4 / 754.0 | 896.4 | 0 / 0 | 0/5 |

CPU values are CPU seconds per full measured round as reported by the harness,
not percentages. Generator CPU/RSS values sum the four client workers. Peak RSS
is the maximum reported across rounds.

| Bytes / clients | Median server CPU s | Peak server RSS KiB | Median generator CPU s | Peak summed generator RSS KiB | Maximum generator lag ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4096 / 256 | 1.89 | 6,012 | 12.45 | 79,124 | 729.3 |
| 65536 / 256 | 1.63 | 6,076 | 9.60 | 93,848 | 5,870.0 |
| 4096 / 4096 | 1.44 | 6,320 | 12.06 | 129,524 | 1,660.5 |
| 65536 / 4096 | 2.31 | 6,368 | 13.25 | 282,244 | 669.2 |

All 20 rounds explicitly report `generator_saturated: true` and `eligible: false`.
The 22 failures in the 64 KiB/256 workload occurred entirely in round 3 and were
all client timeouts; that round reported 5.87 seconds maximum generator lag.
The 720 failures in the 4 KiB/4096 workload occurred entirely in round 1 and
were non-timeout failures; its reported maximum generator lag was 1.63 seconds.
The canonical harness retains counts, not exception types, so the latter cause
has not been established. A generator stalled after TCP setup could encounter
the required one-second accept-to-header deadline, but that is an unproven
hypothesis. The remaining 18 rounds had zero failures.

There is no eligible before/after performance comparison and no claim of a
demonstrated speedup, maximum throughput, complete reliability under the declared
load, or successful performance validation. Additional measurements on an
uncontended machine, with diagnostic failure classification, are needed.

The standalone diagnostic was also rerun inside `references/run_diagnostic.py`;
all checks passed. Sandboxed rerun metadata and logs: `.runs/references/stage-01-cpp/sandbox-focused-002/`.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 2/4 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-01-cpp/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
