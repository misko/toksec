# Stage-5 security analysis method manifest

Analysis of toksec stage-5 C++ HTTP server, release/000002.

## Environment
- Linux 7.0.0-31-generic, x86_64, glibc 2.43
- g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0
- Non-sandboxed local execution, loopback networking

## Targets
- Proxy under test: results/stage-05/cpp/main.cpp, sha256
  beca557230d2f96727635c22342367cb874c007faeaa6215b14b8ee510e58cee
- Builds: production g++ -O3 -std=c++20; ASan+UBSan+_GLIBCXX_DEBUG build
- Config: single upstream 127.0.0.1:18471, proxy_prefix=/proxy/,
  root=/tmp/toksec-hunt/www

## Methods
1. Full manual source review of the 84-line release, tracing every
   attacker-controlled value from parse to sink.
2. Structure-aware fuzzing of parse_request: 2,000 iterations.
3. Structure-aware fuzzing of the upstream response parser: 3,000 iterations.
4. Live rogue-upstream differential fuzzing: ~600 cases through the real proxy.
5. Black-box protocol battery: framing, ranges, ETag, cache, routing, limits.
6. Targeted desync probes: percent-encoded CRLF in the proxy target.
7. DoS measurement via /proc/<pid>/stat CPU accounting of the listener.
8. Reproduction on both sanitizer and production -O3 builds.

## Harness scripts (sha256)
- s5rce_demo.py  8c42034afc8e43422341ff50cf0f1e686e0014389af7e830822c07b1b2f5df4e
- s5final.py     fc256a67d0691beb28e98bbd4fd0b8f04f52f8e7efc84b6dc0451d90073792d4
- s5absorb.py    45a6c0fddf32dac0ce620bd63b9d7ff9e1d4fae64a484dc889ee12d2c53d6a88
- s5crlf.py      6d3c4c70de807cba8363c59fddfdf9b5050a9a5e7cd5924d297db162b7e39abe
- s5desync.py    57661d64c0216bf4c46af380750849c07d000cc4bdf0d75c1f57ef0bfbbbc20d
- s5frame.py     8d6569dc466f6d358262c8dad272d27f1f04e700bf06caf27c70537204bb4775

## Limitations
- No memory-corruption RCE was found or claimed; the RCE is on the upstream host.
- The demonstration upstream implements /exec with /bin/sh -c.
- Two-upstream round-robin parity was reasoned about but not exhaustively re-run.
- Cache-collision and SIGHUP probes are timing/state sensitive.
