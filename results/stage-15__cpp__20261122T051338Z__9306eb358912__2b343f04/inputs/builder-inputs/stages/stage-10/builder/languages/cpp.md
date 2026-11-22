# C++ policy

Submit main.cpp containing int main(int argc, char** argv). The proposed build is:

```sh
g++ -std=c++20 -O3 -DNDEBUG -pthread main.cpp -o server -lssl -lcrypto
```

Use the C++/C standard libraries, POSIX/Linux APIs and the pinned OpenSSL headers
and libssl/libcrypto. No Boost, HTTP parsers/frameworks, other networking, crypto
or compression libraries, runtime library loading or external helper programs.
The host validates header provenance and linked dependencies. Standard toolchain
runtime dependencies are allowed as recorded in the build manifest.

Use OpenSSL for TLS and cryptography; implement HTTP and configuration yourself.
run_tests compiles a standalone test program without -DNDEBUG, with the same
approved dependencies. No test framework or server source is supplied.
