# Stage 2 Rust reference

Implemented and API-validated on 2026-11-14. Performance validation is pending coordinated benchmark resources; no throughput or latency advantage is claimed.

Final source: `references/stage-02/rust/main.rs`

Source SHA-256: `bc395f4b2b02ce34ab9fbc5ebeb0e68ffed83f976c1ab5993f4c0fdbe46b85ae`

## Architecture and contract handling

A single nonblocking Linux `epoll` event loop serves concurrent connections on one CPU. Each connection has one active response and at most one header under construction. `recv(MSG_PEEK)` finds the current header boundary; the server consumes only that header, leaving later pipeline bytes in the socket until the response completes. This conservative queue bound of one is within every positive configured `pipeline_depth`, including one, and permits arbitrarily longer legal bursts through backpressure. Per-dispatch work is bounded to 256 KiB and 32 response iterations.

The parser checks CRLF framing, NULs, token header names, folded headers, exact request-line/version syntax, opaque byte-valued headers, local request framing, and case-insensitive Connection tokens. It supports GET and HEAD, explicit response lengths and connection headers, HTTP/1.0 close, HTTP/1.1 persistence, sequential/pipelined ordering, configured request-count closure, and nonfatal malformed/disconnected clients.

A monotonic timer sweep enforces the first-read-byte absolute header deadline, idle waits, and stalled-write deadlines. Sweep resolution is at most 10 ms and decreases with configured timeouts. Successful writes advance the write-progress timestamp. Connection admission is counted explicitly, with excess accepted sockets immediately closed. The listen backlog scales with configured connection capacity, subject to the operating system cap.

Paths are decoded once as UTF-8 after stripping the query. Invalid escapes, literal fragments, absolute form, NULs, and backslashes fail. Decoded `..` components fail before lookup. Component-by-component `openat(O_NOFOLLOW|O_NONBLOCK)` prevents symlink traversal and blocking FIFO opens; metadata rejects directories and other nonregular objects. File accesses remain relative to the open root directory.

A bounded 128-entry cache holds immutable files. Files of at most 64 KiB are cached as shared byte arrays and transferred with `writev`; larger files retain shared file descriptors and use explicit-offset `sendfile`. Cached bytes occupy at most 8 MiB. Request memory is bounded by the configured header limit plus fixed scratch space, and no large response body is accumulated per connection. A final response shuts down the write side and discards at most 64 KiB of pending input to avoid resetting ordinary excess pipelines at `max_requests`.

Unsafe FFI is limited to Linux `epoll_create1`, `epoll_ctl`, `epoll_wait`, `recv`, `writev`, `sendfile`, `openat`, `listen`, and `signal`, plus ownership transfer of returned descriptors into `File`. SIGPIPE is ignored so abandoned readers produce I/O errors. There are no third-party dependencies, runtime library loading, subprocess servers, or paid model calls.

## API and independent correctness evidence

Every build/API command was run with `taskset -c 3`. The final evaluator compilation used Rust 1.99.1, edition 2021, optimization level 3, and produced no compiler diagnostics. The existing binary policy also passed.

| Evidence | Source SHA-256 | Result |
|---|---|---|
| `.runs/references/stage-02-rust/api-001/result.json` | `f8905549038045edac71a520917d42bf0e34f6bf621382fd30aa74f458fea6be` | Build and 21/21 API checks passed |
| `.runs/references/stage-02-rust/api-002/result.json` | `a045b1b0aa86d9f8c35843954ae331da4f62f809409534774863879ba66c41a2` | Build and 21/21 API checks passed after graceful-close fix |
| `.runs/references/stage-02-rust/api-003/result.json` | `bc395f4b2b02ce34ab9fbc5ebeb0e68ffed83f976c1ab5993f4c0fdbe46b85ae` | Final build and 21/21 API checks passed |
| `.runs/references/stage-02-rust/contract-001/result.json` | Initial implementation | 7/8 probes passed; retained excess-pipeline TCP-reset failure |
| `.runs/references/stage-02-rust/contract-002/result.json` | After graceful-close fix | 8/8 probes passed |
| `.runs/references/stage-02-rust/contract-003/result.json` | `bc395f4b2b02ce34ab9fbc5ebeb0e68ffed83f976c1ab5993f4c0fdbe46b85ae` | 8/8 probes passed against the final evaluator-built executable |

The final independent test executable SHA-256 is `84f4e4ae3b3cf7538116d1f7499a1031c958e7257b3214b50518e91fbbf83c75`. Evaluator output directories retain the corresponding source snapshots and executable artifacts.

The 21 supplied API cases cover ordinary/empty/binary/large files; missing files; query stripping and decoding; confinement; byte fragmentation; syntax; body framing; exact 8192/8193-byte header boundaries; absolute header deadlines; disconnect recovery; headerless HTTP/1.0; HEAD; persistent pipelines; connection tokens; request/idle limits; slow-client fairness; byte-valued headers; configured connection capacity, write deadlines, and pipeline backpressure; and invalid configurations.

`references/stage-02/rust/contract_checks.py` adds eight independent integration probes using its own listeners and fixtures:

- A nine-request burst with `pipeline_depth=1` and `max_requests=7`, checking seven ordered responses, the final close header, and orderly EOF.
- HEAD for missing and 8-MiB files followed by GET on one pipeline, checking status, representation length, and framing.
- One-pass decoding, nested symlinks, FIFO rejection, dot components, trailing `/.`, and stripped query values.
- Stray CR, bare LF, malformed header/method tokens, ambiguous lengths, custom valid methods, and non-UTF-8 header values.
- Configured header limit of 128 bytes: exact limit accepted, 129 rejected.
- Absolute 120-ms fragmented-header and 150-ms idle deadlines.
- A stopped 8-MiB reader with a 120-ms write deadline and one connection slot, followed by successful new service.
- Invalid ports, relative/non-directory roots, negative/overflowing/nondecimal limits, zero pipeline depth, and duplicate configuration keys.

Reproduce final validation from the repository root with a fresh output directory:

```sh
taskset -c 3 python3 evaluate.py --section api --level 2 --language rust \
  --source references/stage-02/rust/main.rs \
  --output .runs/references/stage-02-rust/api-NEW

taskset -c 3 python3 references/run_diagnostic.py \
  --output .runs/references/stage-02-rust/contract-NEW -- \
  references/stage-02/rust/contract_checks.py \
  .runs/references/stage-02-rust/contract-NEW/checks \
  .runs/references/stage-02-rust/api-003/candidate/server
```

## Performance status and limitations

The full declared eight-workload, five-round matrix has not yet been run for this reference. The coordinator is reserving exclusive benchmark resources and has reported host load/generator saturation affecting other measurements. No throughput, p50/p95/p99 latency, failure/timeout, CPU/RSS, round-spread, or eligibility numbers are available for this source yet. Performance claims remain unvalidated until measurements complete; saturated generator measurements will be reported as inconclusive.

The implementation targets the provided 64-bit Linux libc interface and assumes immutable regular files as specified by the contract. Header deadlines begin when backpressure permits reading the first byte of a header. Small-file cache misses synchronously read at most 64 KiB before returning to the event loop. Finite correctness tests do not prove every contract behavior or maximum performance. No supplied contract, harness, evaluator, or other reference implementation was changed.

The standalone diagnostic was also rerun inside `references/run_diagnostic.py`;
all checks passed. Sandboxed rerun metadata and logs: `.runs/references/stage-02-rust/sandbox-focused-001/`.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 6/8 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-02-rust/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
