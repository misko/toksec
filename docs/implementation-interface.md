# Implementation interface: Stage 1

A from-scratch builder receives the contract, public evaluator source and tools,
but no Rust starter or earlier implementation. The source deliverable is one
UTF-8 file named `main.rs`, at most 1 MiB, including `fn main()`.

## Build

Submit the complete file through `submit_candidate`. The trusted controller builds
it inside a sandbox with Rust edition 2021, optimization level 3 and no debug info.
Rust std and direct libc OS calls via declared FFI are permitted. Cargo build
scripts, proc macros, downloads, subprocess servers, HTTP frameworks and parser
libraries are outside the allowed interface. There is no required internal Rust
function signature beyond a compilable executable entry point.

## Process

The evaluator invokes:

```sh
/candidate/server --config /fixtures/server.conf
```

Read the given UTF-8 `key=value` configuration and bind within two seconds. Blank
lines and `#` comments are allowed. Unknown, duplicate, missing or malformed values
must cause a nonzero exit before listening. The standard configuration is:

```ini
listen=127.0.0.1:8080
root=/www
max_connections=8192
header_bytes=8192
header_timeout_ms=1000
idle_timeout_ms=2000
write_timeout_ms=2000
max_requests=100
pipeline_depth=16
```

The evaluator may vary these values. Do not hardcode paths, ports, fixture contents
or limits. Some shared configuration keys matter more in later levels, but all
listed keys are required in this profile.

The server has one CPU, a 512 MiB address-space limit and a 16,384-descriptor limit.
Compilation has separate limits: 4096 MiB address space, 60 CPU seconds and 120 wall
seconds. The server sees read-only candidate and fixture directories, `/www`,
system runtime libraries and temporary scratch space. Host credentials are absent.

## HTTP

Serve GET over HTTP/1.0 and HTTP/1.1. Return exact regular-file bytes beneath the
configured root, explicit Content-Length and Connection: close; close after one
response. The [complete frozen contract](../tasks/v4/level-1.md) specifies status
codes, path decoding/confinement, request framing, malformed inputs, deadlines and
configuration validation. The public suite contains 12 named cases.

The performance section runs only after the API suite passes. It tests fresh
connections, 4 KiB and 64 KiB responses, and 256 and 4096 clients, with five rounds
per workload. Throughput, latency, errors, timeouts, CPU/RSS and generator validity
are recorded. No particular implementation architecture is mandated.

## Git submission

With no starter there is no initial working release. Submit a small working
implementation first, then call `init_repository` to create and tag the private
repository. Call `release_candidate` after validated milestones. Every release
contains `main.rs` plus controller-generated `release.json` metadata. Tags are
numbered `release/000001`, `release/000002`, and so on. The last completed tag is
the graded submission; untagged candidates do not replace it. The instructions also
award partial credit for validated progress shown by periodic tags, with before/after
evidence in release notes. Extra tags without demonstrated progress earn no credit.
This is a qualitative progress rubric; numeric milestone weights are not currently
implemented in the evaluator.

The independent grader extracts tagged source, recompiles it and runs the public
suite. It does not trust a supplied executable or the model's claim that tests pass.
No tag means no graded submission. Instructions alone cannot guarantee a release
if the run is stopped before its first successful publication.

For a human or automation, the corresponding evaluator commands are:

```sh
./evaluate.py --section api --level 1 --source main.rs
./evaluate.py --section performance --level 1 --source main.rs
./evaluate.py --section performance --run RUN_PATH
```

The model currently has bounded tool access rather than a general shell. The CLI
is the trusted external entry point and uses the same public evaluation machinery.
