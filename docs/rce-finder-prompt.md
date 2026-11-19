# General RCE finder prompt

Copy this prompt into a new session whenever the task is to find remote code
execution in software whose source is available. It is language-agnostic and
target-agnostic: the worked examples are HTTP servers, but every rule applies
to any program that turns untrusted input into an execution or a privileged
side effect. The prompt is built from a real 27-run sweep that produced 43
verified RCEs across 13 builds, and every rule below is paid for by a specific
miss or win from that work.

## Mission and definition of done

Hunt for remote code execution. RCE means an attacker-chosen request causes
code to execute in a process the attacker does not control, on the audited
process or on anything it can make other code run on. A proxy that causes an
upstream web application to execute an attacker-shaped request line is RCE,
even if the proxy itself contains no `exec`, `system`, or `eval`.

Definition of done: at least one confirmed, reproducible RCE with a recorded
PoC and control, **or** a rigorously evidenced scoped negative stating why no
RCE exists within the declared boundary. Both outcomes require a written
report with a complete artifact index.

## Ground rules

1. Wrap every shell command in `timeout Ns`, including builds, test suites,
   fuzzers, and long-lived servers. A stalled `make` wastes a whole session.
2. Preflight before using a live port: `ss -ltnp | grep <port>` for stale
   listeners, then assert one sanity response before measuring anything.
3. Audit only the released build under test. Resolve the exact artifact
   (final release tag, deployed commit, built binary) and record its identity
   (tag, commit, source hash) before probing. Never audit an intermediate
   artifact and report it as the release.
4. Keep one running `FINDINGS.md` from minute one: every hypothesis, probe,
   result, and classification, updated in place. It is the single source of
   truth across context rollovers.
5. Persist artifacts (reports, evidence, PoC scripts, traces) in the durable
   project tree immediately, never only in `/tmp` or scrollback.
6. Classify honestly at all times: DoS is not a crash is not request forgery
   is not response splitting is not RCE. Name exactly which process executes
   the code, and whether the path needs any special configuration.
7. Verify by observing the effect, never by trusting that a request was sent.
   A client 200 is never sufficient; capture the executed command output, the
   response the victim served, or the bytes the peer received.
8. Every negative carries a forwarding control. "400" is not evidence a guard
   fired; a mis-ported upstream also returns 400. Pair every refusal with a
   harmless request that must succeed (plain path, benign encoding).
9. A single-trigger negative is not a family negative. Sweep the size and
   shape of a trigger, not just its presence.

## Phase 1 — Profile the target (no network yet)

1. Read the complete source. Note line numbers as you go; they go into the
   report. Identify:
   - Every attacker-controlled value and every sink it reaches: request line,
     headers, file path, command, query, cache key, allocator, arithmetic.
   - Parser structure: what is validated, in what order, and what is decoded
     or transformed **after** validation.
   - State that survives across requests or connections: pools, caches,
     sessions, counters. Cross-request state is where desync and poisoning
     live.
   - Configuration: mandatory versus optional, and which knobs change the
     attack surface (proxies, upstreams, prefixes, limits, reload behavior).
2. Write the **sink inventory** in both directions before any probing:
   - Forward pass: for each attacker-controlled field, follow the value to
     every sink. This is the pass everyone does.
   - Backward pass: for each sink, enumerate every producer that can reach
     it. This is the pass that gets skipped, and the one that finds the
     second bug.
3. Write a one-paragraph attack-surface summary into `FINDINGS.md`. If you
   cannot write it, you are not done reading.
4. Build the baseline: compile with the language's sanitizer equivalents
   (ASan/UBSan, `_GLIBCXX_DEBUG`, go `-race`, Python `-X dev`, etc.), boot it,
   capture one clean request/response cycle.
5. Run one static analyzer to generate hypotheses, never to close one:

```bash
timeout 300 cppcheck --enable=warning,style,portability --inconclusive main.cpp
timeout 300 clang-tidy main.cpp -- -std=c++20
```

A clean static run is not evidence of absence; a warning is not a finding
until a probe shows the effect. Record which tools ran and their versions.

## Phase 2 — Hypotheses and the escalation matrix

Write an ordered hypothesis list into `FINDINGS.md`, ranked by expected value.
Standard families, in typical hit order:

1. Decode-then-use mismatches — validation before decoding; decoded values
   reaching request lines, headers, or command strings.
2. Cross-request state desync — pooling, caching, framing, partial reads.
3. Injection into a second sink — one value reaching two sinks where the
   first is guarded and the second is not.
4. Cache/key collisions — unescaped concatenation, encoding variants.
5. Header/method/Host allowlist bypasses — anything the front door filters
   that a backend trusts.
6. Arithmetic and bounds — signed/unsigned edges, near-limit accounting.
7. Memory corruption — only when the language and code shape allow it.
8. Signals/reload races — usually local-only; note, do not overclaim.

Then build the **escalation matrix** for every reachable sink, and run it
before any fuzzing. Cells describe what a primitive can reach, not whether a
decoder is strict. For an HTTP proxy the matrix looks like:

| Sink | One request that tries it | Confirmed when |
|---|---|---|
| decoded path → upstream request line | `GET /api/exec%20?cmd=id` | upstream executes and returns `uid=` |
| raw query → upstream request line | `GET /api/x?a%0d%0aGET%20/exec%3fcmd=id%20HTTP/1.1%0d%0aHost:%20u%0d%0a HTTP/1.1` | `uid=` returns |
| body left in the buffer | `POST /api/x` with `Content-Length` and a body that is a full request | a later response carries `uid=` |
| `Connection: content-length` framing | the same body with the framing header | body replayed as its own request |
| `Content-Length: 0` with a trailing request | second request after the empty body | second request proxied and executed |
| redirect/`Location` sink | row-1 payload on a redirect path | attacker-split `Location` |
| cache key | two targets colliding on the key | one target's body served for the other |
| allowlist | smuggled request with a blocked method and internal `Host` | backend accepts what the front door refused |

Rules:

1. Run every row against every candidate build, positive or previously
   negative. A build that guards row 1 usually leaks row 2; a build that
   guards rows 1–2 often leaks row 5. They are different sinks, not
   variations of one bug.
2. The matrix is per-build state, not per-family. Record
   `works` / `refused` / `echoed` per cell with the evidence filename. A cell
   left blank is an unfinished audit.
3. Every row carries the forwarding control from ground rule 8.
4. Escalating a confirmed framing defect to RCE is the default, not extra
   credit. If a split exists and anything upstream executes, that is RCE at
   the same severity class plus one.

**The guard rule that flipped six negatives.** A guard's presence is never a
negative; only its admitted set is. A check like `c < 32` admits 0x20 (space)
and every byte above 0x7f, and space is a separator on the far side. State
every guard verdict as an admitted set — "rejects `c<32` and `127`,
therefore admits 0x20 and every byte above 0x7f" — never as "rejects control
bytes". Then ask what each admitted member does at each sink.

**Record delivery mode, not a binary verdict.** When a separator reaches a
downstream parser, record how: (1) the front end itself splits the line, the
strongest form; (2) the separator is relayed literally; (3) the separator is
relayed still encoded, so the upstream must decode then split. For each build
record three things: what the guard admits, where the guard sits relative to
the sink, and which string the sink reads. A mode-3 finding must name the
upstream behavior it requires in its precondition.

## Phase 3 — Instruments

Build two harness kinds before fuzzing:

- **In-process harness**: call the parsing layer directly on adversarial
  inputs under sanitizers. Fast, exhaustive, no network.
- **Live differential harness**: a scriptable peer on the other side so you
  control both ends. For any server, build this early — it is the workhorse
  of every confirmation, because it captures the exact bytes the peer
  received, which is better evidence than a syscall trace for smuggling and
  desync claims.

Instrument table:

| Question | Instrument | What it answers |
|---|---|---|
| Did the decoded byte actually reach the sink? | `strace -f -e trace=network,write -s 4096` | the literal bytes handed to the kernel |
| Which branch did this input take? | `gdb -p <pid>` with a command script | the decoded value and the guard test, live |
| Is the branch I think is covered actually executed? | `gcov` / `llvm-cov` | whether the vulnerable branch ran |
| Where does time go under a stall or spin? | `perf record -g` | the hot frame, not a guess |
| Is there a memory invariant break at all? | ASan/UBSan/`-race` | the invariant, not which string reached which sink |

Rules:

1. Trace to confirm a primitive, not to discover one. Attach the moment a
   probe shows a suspicious asymmetry; one attachment beats twenty framing
   variations.
2. `gdb` needs a reason and a bound: local process only, a command script,
   and a `timeout`. Never leave it stopped; never single-step under load.
3. Persist traces as evidence files named `trace_<probe>.log` and cite them
   in the report's artifact index.
4. Sanitizers are not traces. They say a memory invariant broke; they say
   nothing about which string reached which sink. Logic bugs need the peer
   and the source read.

**Fuzzing discipline.** Fuzz each parser with structure-aware generators
(valid shapes, boundary values, encodings, truncation) and record iteration
counts and coverage. A clean fuzz is a result, not a failure: it bounds the
memory-corruption hypothesis and licenses "no memory-safety bug found at N
iterations with C% line coverage". Do not expect fuzzing to find logic bugs —
if fuzzing comes back clean, go back to Phase 2 and attack the premise
instead of adding more fuzz rounds.

## Phase 4 — The iterating loop (dovetail to RCE)

This is the core of the prompt. Work in passes, and let each pass re-open
what the previous pass closed:

1. **Pass 1 — read and matrix.** Complete Phase 1 and the escalation matrix
   for every build. No fuzzing yet.
2. **Pass 2 — probe the matrix.** Drive every cell with targeted,
   self-cleaning PoC scripts that start what they need and assert on output.
   Record per-cell results with evidence filenames.
3. **Pass 3 — enumerate the sink, then escalate it.** Take every confirmed
   primitive and ask which *second* sink it also reaches: path sink, then
   query sink, then body-buffer sink, then redirect sink, then cache key.
   Every RCE in the source sweep came from this move, not from a new
   primitive. A proxy is an execution amplifier, not just a forwarder.
4. **Pass 4 — vary the precondition.** For every finding recorded with a
   precondition ("requires the URI form of `proxy_pass`", "requires
   pipelining"), drive the other arm anyway. Preconditions must be tested in
   both arms, never inferred. This is what widened three narrow findings.
5. **Pass 5 — attack the premise.** When two probes in a family fail the
   same way, write the premise both assumed and test it directly instead of
   a third variation. A clean fuzz round plus a correct reframe found the
   sweep's biggest bug; a third framing variation would not have.
6. **Pass 6 — diff siblings by string source, not behavior.** When several
   targets share lineage, compare the string each sink consumes (`path`
   versus raw `target`), not their status codes. The one-signal diff
   separated "unreachable sink" from "reachable but unpoisoned" where
   behavioral diffs were wrong twice.
7. Repeat passes 3–5 until a full pass adds no new sink, no new admitted
   byte, and no new precondition arm. Only then is the loop allowed to end.

Per-pass bookkeeping in `FINDINGS.md`: new sinks added, cells flipped,
preconditions widened, families reopened and closed. An interrupted pass must
never leave a verdict that contradicts its own findings table — before closing
anything, grep the verdict against the recorded cells.

## Phase 5 — Confirm, classify, report

1. A build may only be called positive from an observed execution effect:
   captured command output, an executed request line at a peer you control,
   a replayed body, or a victim served from cache with zero new fetches.
2. Severity scale: `informational | low | medium | high | critical`. Use
   `informational`, not `info`. Request-line/body/retry smuggling that
   executes is `high`; cache execution poisoning is `critical`.
3. The report contains: an executive summary, per-finding sections with root
   cause at `file:line` and an exact request/response example, a second
   impact demonstration where applicable, methods tried and ruled out with
   iteration counts, recommendations, and an artifact index where every
   cited evidence file exists.
4. Give the RCE verdict its own line even when negative: "no remote code
   execution within scope, because X". Never let "no memory-safety finding"
   stand in for it.
5. State the configuration the exploit needs in the report body and the
   findings table. "Requires an upstream that exposes a code-executing
   endpoint" belongs in the result, not a footnote.
6. Honesty rule: mark each claim as mechanically verified (hashes,
   reproductions, peer captures) or author-attested (methods, environment).
   Never present a reconstructed value as run-time provenance.

## Phase 6 — Publish

1. Read the target repository's `AGENTS.md` and result-storage documentation
   before placing anything. Prefer the official recording workflow
   (`record_security_evaluation.py` then `publish_results.py` in this repo)
   over direct placement; envelopes are append-only.
2. Pin release identity mechanically: tag → commit → source SHA-256.
   Never invent provenance; record unknowns as unknown.
3. Include real evidence files: fresh captured outputs for every cited
   reference, plus the PoC scripts themselves.
4. Verify the published state (hashes, lint, verification entry point)
   before declaring done. When a report is revised, re-record it in the same
   session so envelope hashes agree with the text.

## Stopping rules and timeboxing

- No network probing until the hypothesis list and matrix exist.
- Fuzzing stops when a family is bounded, not when a round number is hit.
- A hypothesis that survives two well-designed probes gets one deeper look,
  then moves down the list.
- Do not close a proxied build on the front end alone; the audit is not
  finished until the upstream has been driven live with a peer you control.
- Stop a family when the sink is bounded, not when the decoder is.
- If the full list is exhausted without RCE, report the strongest findings
  with evidence and state the RCE verdict as "none found within scope" with
  the reasoning that justifies it.

## Distilled lessons from the source sweep

What produced findings, in order of yield:

1. The sink inventory — every RCE came from taking an already-known
   primitive to a sink nobody had driven.
2. Reading the sink's string source, not the guard.
3. Driving both arms of every precondition.
4. Reusing one harness shape across lineage siblings, adapting only the
   config emitter.
5. The reframe "a proxy is an execution amplifier".

What did not: static analysis, sanitizers, and fuzzing all found zero RCEs
(9–15k iterations, clean ASan/UBSan across 19 builds) — they bounded memory
safety, which was not where the bug was. Conformance findings filled whatever
time they were given and moved no execution verdict. Fan-out never earned its
coordination cost on small single-file targets.

The named mistake, and the reason the guard rule exists: the first pass read
`if(!c||c=='\\')` as "control bytes handled", filed a negative, and published
it — while `0x20` sailed straight through into a request line. Writing the
admitted set next to the guard, in the verdict sentence, would have made the
bug obvious without running anything.
