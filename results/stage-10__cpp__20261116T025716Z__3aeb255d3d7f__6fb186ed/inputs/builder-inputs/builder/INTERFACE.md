# Source, process and fixture interface

Submit one UTF-8 main.cpp or main.rs, at most 1 MiB, through submit_candidate.
The controller compiles and runs it in a sandbox. No additional implementation
files, downloaded dependencies, HTTP libraries or previous implementations are
provided. Approved OpenSSL is the sole TLS dependency exception. See your language
policy and TLS.md. Compiler and library identities belong in the run manifest.

Launch the master as `/candidate/server --config /fixtures/config/nginx.conf`.
`--check-config PATH` validates configuration, includes, roots and TLS material,
prints a diagnostic on failure, and exits without binding or forking workers.
Exit zero means valid; a nonzero exit means invalid. Diagnostics identify file
and line where possible and never print private key contents.

Initial startup must make all configured listeners serviceable within five seconds.
The master remains foreground; do not daemonize. SIGTERM to the master starts a
bounded graceful drain. SIGHUP requests transactional configuration/certificate
reload. OPERATIONS.md defines worker replacement and generation semantics.

The host mounts these fixture paths in each test sandbox:

| Path | Access and use |
|---|---|
| /fixtures/config | Read-only to candidate; host may replace files for reload tests |
| /fixtures/tls | Read-only test-only certificate chains, leaf private keys and CA certificate |
| /www | Read-only immutable files, with alternate roots and aliases in tests |
| /tmp | Private writable scratch, capped at 64 MiB by the host |
| /candidate | Read-only source snapshot and executable |

The supplied sample files demonstrate inputs. Host fixtures vary names, content,
ports and limits within the contract. Do not hardcode sample values. No host
credentials, CA signing private key, reference server or hidden checker is mounted.
Upstream fixture services are reachable only in the sandbox's private network.

The process tree receives 1, 2 or 4 CPUs as declared in each measurement profile,
512 MiB aggregate charged memory, 16,384 total live file descriptors, and at most
one master plus four worker processes. The host includes mapped OpenSSL and
charged scratch/cache memory in the resource budget; it must publish the exact
memory-accounting method. Do not interpret per-process limits as separate budgets.
Compile limits remain 4096 MiB address space, 60 CPU seconds and 120 wall seconds.
Aggregate enforcement must pass host preflight before any run is authorized.

The source may fork workers from itself but may not execute external programs or
delegate HTTP/TLS/configuration parsing to another executable. IPC, shared memory,
threads, POSIX/Linux I/O and the approved TLS C ABI are allowed. Worker thread
counts and descriptors remain inside the aggregate resource budget.

Controller tools retain their existing names: budget_status, submit_candidate,
revalidate_candidate, run_tests, benchmark_candidate, init_repository,
release_candidate and finish. Tests are your own standalone programs run in the
same isolation policy. They must create their own listeners and fixtures.
The controller owns compilation, Git initialization/tagging and release evidence.
These tool names describe the intended Stage 10 interface, not current support.
