# Stage 1 Rust reference

Status: implemented and API validated. Full-matrix performance measurement is
pending the coordinator's exclusive resource assignment; no throughput or latency
claim is inferred from the architecture.

Final source: `references/stage-01/rust/main.rs`.

SHA-256: `7de049780c1f1c9e789955a961a01e7e43226a98db69a5f7ec9cbfa24b655ebf`.

## Implementation

The server uses one nonblocking Linux epoll event loop. It accepts at most 128
sockets per listener event, limits each file-write turn to 256 KiB, and tracks one
deadline per pending connection in a bounded ordered timer set. The header
deadline starts when accept returns and is checked before every receive iteration,
including clients sending no bytes and clients that remain continuously readable.
Slow readers wait for writable readiness without blocking other connections.
Each accepted request receives one response with an explicit Content-Length and
Connection: close.

The parser validates request lines, method/header tokens, CRLF framing, field
values, versions, body framing, and the configured complete-header byte limit.
Paths are query-stripped and percent-decoded once, validated as UTF-8, and checked
for traversal, NUL, backslash, and fragment syntax. Files are opened relative to
the configured root descriptor with openat and O_NOFOLLOW for each component.
Intermediate descriptors are checked for symlinks and directories. Final files
are opened nonblocking, checked for regular-file type, and never served through a
symlink. Directory and nonregular targets return 403.

Immutable successful responses up to 64 KiB can share a complete response buffer.
The cache is limited to 256 entries and 16 MiB, including path and response bytes.
Larger files and responses exceeding that cache budget use sendfile with partial
write tracking. Cache insertion occurs only after normal parsing and secure file
opening. Request/filename values receive no fixture-specific treatment.

Errors send a FIN and briefly drain excess incoming bytes, up to a 250ms deadline,
so an oversized header or rejected body does not turn its response into a TCP
reset. All connection buffers, file descriptors and timer entries are dropped on
completion, timeout or disconnect. The configuration's Stage 1 unused persistent
connection settings are still required and validated.

## Unsafe and platform details

The program uses only Rust std and directly declared Linux libc calls:
epoll_create1, epoll_ctl, epoll_wait, accept4, listen, recv, send, sendfile,
shutdown, openat and signal. Linux epoll_event uses its packed x86-64 ABI. Event
fields are copied rather than borrowed. Buffers and CString pointers remain valid
for each synchronous call, and every successful descriptor is immediately
transferred to an owning Rust descriptor/File. SIGPIPE is ignored because sendfile
does not expose MSG_NOSIGNAL; ordinary sends use MSG_NOSIGNAL.

The implementation targets the evaluator's Linux x86-64 environment. It does not
load runtime libraries or invoke subprocesses. Compilation passed the evaluator's
binary policy checks without warnings.

## API and additional correctness evidence

All compilation, API and focused diagnostic commands were pinned to CPU 1. The
full applicable host suite and its case selection were inspected before writing
the implementation. No evaluator, contract or other reference source was edited.

| Evidence | Source SHA-256 | Outcome |
|---|---|---|
| `.runs/references/stage-01-rust/api-001/result.json` | `0cc458f6f739e19d893d9372c18f21586cea969ab5b33543d023decd23b9b57c` | 11/12; header-limit case exposed an unread-byte TCP reset. Retained. |
| `.runs/references/stage-01-rust/api-002/result.json` | `a04a3233f72952c9ba08ce1ccc1a43f6fe849b3a782d7a6e4f846c835d96ff2b` | 12/12 after graceful error close. |
| `.runs/references/stage-01-rust/edge-001/result.json` | `a04a3233f72952c9ba08ce1ccc1a43f6fe849b3a782d7a6e4f846c835d96ff2b` | 9 additional diagnostic groups passed. |
| `.runs/references/stage-01-rust/api-003/result.json` | `7de049780c1f1c9e789955a961a01e7e43226a98db69a5f7ec9cbfa24b655ebf` | 12/12 after checking the deadline within continuously readable receive loops. |
| `.runs/references/stage-01-rust/edge-002/result.json` | `7de049780c1f1c9e789955a961a01e7e43226a98db69a5f7ec9cbfa24b655ebf` | 12 additional diagnostic groups passed. |

The final full API evaluation covered ordinary, empty, binary and 2 MiB files;
query and one-pass decoding; traversal and symlinks; byte fragmentation; HTTP
syntax; request framing; exact 8192-byte header acceptance and 8193-byte rejection;
the absolute header deadline; abandoned clients; HTTP/1.0 without headers; and
invalid configuration rejection.

`references/stage-01/rust/edge_cases.py` retains additional tests run through the
existing runtime sandbox. These cover HTTP/1.1 without Host, client write-half
close, Content-Length overflow/duplicates/whitespace, transfer coding variations,
malformed tokens/control bytes, unknown methods, valid and invalid Unicode,
encoded literal percent sequences, encoded question/hash filename characters,
intermediate and dangling symlinks, UNIX sockets, FIFO and directory targets,
silent and trickling header deadlines with concurrent valid service, a stalled
16 MiB response reader, abandoned sockets, and exact 64 KiB payloads. A separate
configuration changes the listen port and root, accepts comments/whitespace,
enforces a 128-byte header limit, and closes a silent client at the configured
90ms deadline. Final API and diagnostic server logs were empty.

Reproduction:

```sh
taskset -c 1 python3 evaluate.py --section api --level 1 --language rust \
  --source references/stage-01/rust/main.rs \
  --output .runs/references/stage-01-rust/api-NEW
taskset -c 1 python3 references/stage-01/rust/edge_cases.py \
  --artifact .runs/references/stage-01-rust/api-NEW/candidate \
  --output .runs/references/stage-01-rust/edge-NEW
```

## Performance evidence and limitations

No benchmark has been launched yet. The required four workloads, each with five
rounds, must still be measured after the coordinator assigns exclusive benchmark
resources. That measurement must retain goodput, payload throughput,
p50/p95/p99 successful latency, errors/timeouts, server CPU/RSS, client CPU/lag,
round spread and eligibility for both 256 and 4096 clients and both payload sizes.
No performance-validation claim is made while this evidence is missing.

The immutable-file assumption is required for the successful-response cache.
Filesystem operations can still wait on storage; the supplied fixture storage is
local. API and finite diagnostic success are evidence of the tested behaviors,
not a proof against all possible malformed input or resource exhaustion.

## Central diagnostic follow-up

The frozen source completed the full declared matrix with the v2 supplemental
native generator, one round per workload. 1/4 rounds were eligible;
measurement failures: 0; warmup failures: 0. See
[central validation](../../validation/README.md) and the source-matched
[compact result](../../validation/stage-01-rust/supplemental.json).
These are supplemental diagnostics, not a five-round canonical performance score.
Earlier handoff statements about pending measurements describe the builder handoff.
