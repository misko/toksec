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

Submit a complete C++ test program with its own main() to either test tool.
The compiler enables assertions. Exit zero for success and nonzero for failure.
run_tests executes that program with its own build directory. run_candidate_test starts
your selected server, then executes the program in a separate sandbox on its
private network. Send HTTP requests to 127.0.0.1:8080. The server uses the
normal stage configuration and public files. The client supplies any upstreams
its test needs. Read the returned build result and the test process exit code.
You choose your implementation, debugging and testing methods.
