# ev_r16_B_census.md — process-owning sink census, 27 runs (26 with published source)

Lane B round 16. Source of truth is the raw run dir: `bin/<family>__<build>` and the byte-identical
`<family>__<build>.cpp` (2usd from `recovery__2usd.cpp`). `level-*` sources are read from
`/home/mouse9911/gits/toksec-next/results/<run>/implementation/releases/<last_tag>.*`.

Verdicts are from source. `absent` = the directive/call does not occur anywhere in the file.
`present` = it occurs, with the line(s). Every build has its own row; nothing is collapsed away.

One of the 27 runs published **no source at all** — `stage-05__cpp__20261116T025716Z__3aeb255d3d7f__6dadb2a4`
(see the last census row). It is carried explicitly as `absent-source` and is counted separately
from the 26 censused sources, so no claim below silently includes it.

This file was written before any driving (orchestrator request) so the closed sink set survives a
stall. It is followed by `ev_r16_B_execproof.txt` per build, which is the empirical half.

## Headline

**No build in the corpus can execute a process.** `system(`, `popen(`, `execv`, `execvp`, `execl`,
`posix_spawn` occur **zero** times in all 26 published sources. The only process syscalls anywhere are
`fork()` and `waitpid()`, and the fork child always calls a C++ function (`worker(...)`), never `exec*`.
The 27th run has no source to hold either, so it adds no spawn path.

Stated plainly:

- Proxy-local execution is impossible in every build. No build can run a shell.
- A "smuggled /exec" is always the **upstream host** executing, never the proxy. The proxy's whole
  process surface is: parse config → `fork` N workers (or spawn threads / run one epoll loop) →
  `accept` → `read`/`write`/`open`/`sendfile`. Nothing else.
- No build writes any file it later reads (`ofstream`/`fopen`/`O_CREAT`/`O_TRUNC`/`rename`/`unlink`
  all zero), so there is no write→exec and no read→exec chain.
- The cache is **in-memory only** — therefore no persistence across a restart, but still
  **cross-client** within a run: an `EXEC:` body installed by an attacker is served to a later
  different victim. That is lane E/F territory; round 15 lane E already showed it live on
  `6baf167b:88` and `ae021893:67`, and the orchestrator confirmed the same wildcard-cache poison on
  `level-5` (line 72 wildcard lookup, line 73 `"|*"` store; evidence
  `ev_r16_ORCH_l5_wildcard_upstream.log`, `ev_r16_ORCH_l5_wildcard_summary.txt`). Lane B cites those
  rather than re-running them.

## Census table

`fork`(line) / `system·popen·exec` / `CGI` / `error_page`→URI / `SSI#exec` / `FastCGI` /
`include` re-read at runtime / log path / pid file / TLS cert reload / request-var→shell.
`re-read` is the only sink that can become a chain, and is graded per build in the second table.

| build | fork | system/popen/exec | CGI | error_page | SSI #exec | FastCGI | include re-read | log path | pid file | cert reload | var→shell |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1cfd33433d25__063b0d5e | present 82 | absent | absent | absent | absent | absent | absent (compile-time only, 21) | absent | absent | absent (SIGHUP=SIG_IGN, 82) | absent |
| 1cfd33433d25__44bf7f35 | present 105 | absent | absent | absent | absent | absent | absent (49) | absent | absent | absent (hup flag read, reload body empty, 105) | absent |
| 1cfd33433d25__5de24666 | absent (single-proc epoll) | absent | absent | absent | absent | absent | absent | absent | absent | absent (no SIGHUP handler) | absent |
| 1cfd33433d25__61cc738c | present 71 | absent | absent | absent | absent | absent | absent (26) | absent | absent | absent (hup flag read, reload body empty, 71) | absent |
| 1cfd33433d25__6baf167b | absent (fixed thread pool) | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 110 | absent |
| 1cfd33433d25__897596e5 | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent |
| 1cfd33433d25__8d2b95ab | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent |
| 1cfd33433d25__afdc173f | absent (thread per conn) | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 82 | absent |
| 1cfd33433d25__e1a28e35 | absent (thread per conn) | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 91 | absent |
| 3aeb255d3d7f__29d05850 | present 60 | absent | absent | absent | absent | absent | absent (24) | absent | absent | absent (SIGHUP ignored in master, 60) | absent |
| 3aeb255d3d7f__32151ad3 | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent |
| 3aeb255d3d7f__6fb186ed | present 75 | absent | absent | absent | absent | absent | absent (41) | absent | absent | absent (no SIGHUP handler) | absent |
| 3aeb255d3d7f__8d5ff1f2 | present 98 | absent | absent | absent | absent | absent | absent (24) | absent | absent | **present** re-read: SIGHUP reloads config AND respawns workers, 98 | absent |
| 3aeb255d3d7f__ae021893 | absent (thread pool) | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 74 | absent |
| 3aeb255d3d7f__ba507497 | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent |
| 3aeb255d3d7f__d0299456 | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent | absent |
| 3aeb255d3d7f__f2b3415b | absent (thread pool) | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 100 | absent |
| recovery__2usd | present 83 | absent | absent | absent | absent | absent | absent (23) | absent | absent | absent (SIGHUP=SIG_IGN, 83) | absent |
| level-1-024bc9088c84 | absent (single-proc `poll` loop, 62; no thread) | absent | absent | absent | absent | absent | absent (root `OpenOptions` 16) | absent | absent | absent (no handler) | absent |
| level-1-0989d5c40297 | absent (single-proc epoll, 40) | absent | absent | absent | absent | absent | absent | absent | absent | absent (SIGPIPE only, 40) | absent |
| level-1-2afe956f08cb | absent (single-proc epoll, 95) | absent | absent | absent | absent | absent | absent (root `OpenOptions` 34) | absent | absent | absent (no handler) | absent |
| level-1-4bdb088ee513 | absent (Rust `thread::Builder` per conn, 38) | absent | absent | absent | absent | absent | absent | absent | absent | absent (no handler) | absent |
| level-1-cc4294cfd485 | absent (single-proc epoll, 83) | absent | absent | absent | absent | absent | absent | absent | absent | absent (no handler) | absent |
| level-2-1d7d52f32031 | absent (single-proc epoll, 48) | absent | absent | absent | absent | absent | absent | absent | absent | absent (SIGPIPE only, 48) | absent |
| level-2-5327b2715c64 | absent (single-proc epoll, 23) | absent | absent | absent | absent | absent | absent | absent | absent | absent (no handler) | absent |
| level-5-a4ba853a82fe | absent (single-proc epoll; the corpus critical) | absent | absent | absent | absent | absent | absent | absent | absent | **present** re-read: SIGHUP re-reads config, 84 | absent |
| stage-05__cpp__20261116T025716Z__3aeb255d3d7f__6dadb2a4 | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source | absent-source |

## Re-read chain table — per build, every row explicit

A re-read file is a write→exec chain only if the server re-reads attacker-controlled bytes AND
something executes on them. There is no executor, so every row terminates in "parsed as nginx
syntax", never a shell. `cache` is listed because it is the only cross-client carrier, and the two
kinds are graded separately: a **proxy body cache** can hand an upstream `EXEC` body to a later
client, whereas a **static-file cache** can only replay bytes that were already on disk.

One trap: four proxied builds (`44bf7f35`, `61cc738c`, `2usd`, `8d5ff1f2`) list
`toksec_cache_ttl`/`toksec_cache_bytes` in their accepted config key set but contain no cache
function, so the knob parses and does nothing. Their rows are `no` on effect, not "unknown".

| build | re-reads anything? | what | cache (cross-client)? | chain to a process? |
|---|---|---|---|---|
| 063b0d5e | no | — | no | no |
| 44bf7f35 | no | — | no | no |
| 5de24666 | no | — | no | no |
| 61cc738c | no | — | no | no |
| 6baf167b | **yes** (config, SIGHUP 110) | operator config | **proxy body** (cached 89, storecache 90, key `host+target+AE` 88) | config only → no |
| 897596e5 | no | — | no | no |
| 8d2b95ab | no | — | static-file only (cache 42, key = path 47) | no |
| afdc173f | **yes** (config, SIGHUP 82) | operator config | **proxy body** (cacheget 77/cacheput 78) | config only → no |
| e1a28e35 | **yes** (config, SIGHUP 91) | operator config | **proxy body** (cacheget 79/cacheput 80) | config only → no |
| 29d05850 | no | — | no | no |
| 32151ad3 | no | — | no | no |
| 6fb186ed | no | — | no | no |
| 8d5ff1f2 | **yes** (config + worker respawn, SIGHUP 98) | operator config | no | config only → no |
| ae021893 | **yes** (config, SIGHUP 74) | operator config | **proxy body** (lookup 69, store 70, key `host+target` 67, no encoding component) | config only → no |
| ba507497 | no | — | static-file only (lookup 37, cache_file 38) | no |
| d0299456 | no | — | static-file only (cache keyed on `x.input`, 44) | no |
| f2b3415b | **yes** (config, SIGHUP 100) | operator config | **proxy body** (cacheget 83/cacheput 82) | config only → no |
| 2usd | no | — | no | no |
| level-1-024bc9088c84 | no | — | no (grep `cache` = 0) | no |
| level-1-0989d5c40297 | no | — | no | no |
| level-1-2afe956f08cb | no | — | no | no |
| level-1-4bdb088ee513 | no | — | no | no |
| level-1-cc4294cfd485 | no | — | no | no |
| level-2-1d7d52f32031 | no | — | no | no |
| level-2-5327b2715c64 | no | — | no | no |
| level-5-a4ba853a82fe | **yes** (config, SIGHUP 84) | operator config | **proxy body, wildcard** (exact-or-`"\|*"` lookup 72, `"\|*"` store 73) | config only → no |
| stage-05__cpp__20261116T025716Z__3aeb255d3d7f__6dadb2a4 | unknown | — | unknown | no source to census |

## Read/write syscall census (evidence for the headline)

- Write syscalls in any shipped server body: **none**. `ofstream`, `fopen`, `O_CREAT`, `O_TRUNC`,
  `rename`, `unlink`, `mkstemp` and `File::create` are 0 hits across all 26 published sources. The
  sole `fs::write` occurrences in the corpus are the four inside the `#[cfg(test)]` harness of
  `level-2-5327`'s *earlier* `release-000002.rs` — the same block that holds its two `connect` hits,
  and not the 24-line shipped last tag. All 26 censused files are last-tag, so no shipped server body
  writes anything at runtime.
- Every open is read-only, and **every open of a request-derived path (the leaf) also carries
  `O_NOFOLLOW`** — that is the one that matters for `..`/symlink reads. The per-build leaf flag
  expressions: `063b0d5e:48`, `44bf7f35:86`, `5de24666:40` (`(last?O_RDONLY:O_PATH)`),
  `61cc738c:65`, `6baf167b:81`, `897596e5:36`, `8d2b95ab:46`, `afdc173f:69`, `e1a28e35:72`,
  `29d05850:49`, `32151ad3:38` (`last?…:(O_PATH|…NOFOLLOW)`), `6fb186ed:63`, `8d5ff1f2:83`,
  `ae021893:56`, `ba507497:46` (both arms), `d0299456:38` (`O_RDONLY|O_NONBLOCK:O_PATH` +
  `O_NOFOLLOW`), `f2b3415b:75`, `2usd:75` — and the level set at `0989:36`, `1d7d:37`, `5327:14`,
  `cc4294:57`, `2afe:76`/`79`, `4bdb:32`/`33`, level-5 `67`.
- The **initial root/directory handle** is the one that usually is *not* `NOFOLLOW`, and it is an
  operator-configured path, not request-derived: **23 of the 26 sources omit it** — the 15 C++
  builds `44bf7f35:86`, `5de24666:44`, `61cc738c:65`, `6baf167b:81`, `897596e5:36`, `8d2b95ab:46`,
  `afdc173f:69`, `e1a28e35:72`, `29d05850:49`, `32151ad3:44`, `ae021893:56`, `ba507497:46`,
  `d0299456:53`, `f2b3415b:75`, `2usd:75`, plus the whole level set (`0989:40`, `1d7d:29`, `5327:7`,
  `cc4294:26`, `2afe:34`, `4bdb:11`, `024:16`, level-5 `67`). Only three include it:
  `063b0d5e:48`, `6fb186ed:63`, `8d5ff1f2:83`.
- So the exact statement is: every open is read-only; every request-derived leaf open carries
  `O_NOFOLLOW`; the root handle is `O_NOFOLLOW` in only 3 of 26. The consequence for this lane is
  nil either way — the root is operator-named, and the leaf (where `..` and symlinks could land) is
  always `NOFOLLOW`. Only `cc4294:26` and `5327:7` open the *config* with plain read-only
  `File::open`; the rest read the config through `ifstream`/`fs::read_to_string`.
- The dynamic symbol set that can start a process, checked on the built binaries: only `fork` and
  `waitpid` appear (`nm -D bin/1cfd33433d25__063b0d5e` → `U fork@GLIBC_2.2.5`,
  `U waitpid@GLIBC_2.2.5`; no `exec*`, `system`, `popen`, `posix_spawn`).
- No `connect()` at all in the six stage-01 builds — they cannot even be an upstream host for a
  proxy-local RCE; they serve static files only. The seven `level-1`/`level-2` builds are the same
  shape: nine config keys, no proxy directive, and no `connect` in the served code. Only `level-5`
  proxies (`connect` 76).
- Caveat for future greps: `level-2-5327b2715c64` does contain two `connect(` and four `fs::write`
  hits, but *all* of them are inside `#[cfg(test)] mod tests` in `release-000002.rs` (its own
  integration harness: `fn conn(port)` at 257, wait-for-bind at 264, fixture writes at 261). The
  shipped `release-000003.rs` (24 lines, the last tag) has zero of either. So a naive `rg -c connect`
  over the level set reports 5327 as a proxy when its server body is not one.
