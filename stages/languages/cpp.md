# C++ build interface

Submit one UTF-8 main.cpp, at most 1 MiB, containing int main(int argc, char** argv).
The evaluator compiles with g++ -std=c++20 -O3 -DNDEBUG -pthread. No build system,
additional source files, downloaded dependencies or custom compiler/linker flags.

Use only the C++ standard library, C standard library and POSIX/Linux OS APIs
such as sockets, epoll/poll, threads, filesystem operations and sendfile.
No third-party libraries, HTTP parsers/frameworks, Boost, networking libraries,
TLS/encryption/cryptography or compression libraries. Do not load libraries at
runtime or delegate to subprocess programs. All five stages serve plaintext HTTP;
there is no encryption requirement and you should not implement cryptography.
The compile harness checks included header provenance and linked dependencies.

run_tests accepts a complete standalone C++ test program with its own main().
It is compiled without -DNDEBUG so assertions work, then executed in the sandbox;
exit zero for success and nonzero for failure. No external testing framework.
You choose your implementation, debugging and testing methods.
