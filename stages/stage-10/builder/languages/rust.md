# Rust policy

Submit main.rs containing fn main(). The proposed build is:

```sh
rustc --edition=2021 -C opt-level=3 main.rs -o server -l ssl -l crypto
```

Use the Rust standard library, POSIX/Linux C ABI and pinned OpenSSL C ABI.
Declare required FFI bindings in your source. OpenSSL headers and API documentation
are supplied as references; no Rust wrapper, networking crate, HTTP parser, Cargo
dependency, build script or implementation source is supplied. Additional runtime
library loading and external helper programs are prohibited.

OpenSSL performs TLS and cryptography. You implement HTTP, configuration, binding
ownership and event handling. The host validates linked dependencies against the
recorded toolchain/OpenSSL runtime allowlist. run_tests compiles a standalone Rust
test program with the same approved dependency policy and enabled assertions.
