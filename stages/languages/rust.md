# Rust build interface

Submit one UTF-8 main.rs, at most 1 MiB, with a Rust executable entry point.
Build: Rust edition 2021, optimization level 3. Rust std and direct libc OS calls
through declared FFI are allowed. No Cargo build scripts, proc macros, downloads,
subprocess servers, HTTP frameworks or parser libraries. Disclose unsafe FFI usage.
Stage 5 additionally permits system OpenSSL and zlib.
run_tests compiles your complete test source using rustc --test.
