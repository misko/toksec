# General RCE finder prompt

Copy this prompt into a new session whenever the task is to find remote code
execution in software whose source is available. It is language-agnostic,
protocol-agnostic, and target-agnostic: it works for a standalone HTTP server,
a library behind a parser, a message-queue worker, a template engine, a
deserializer, or anything else that turns untrusted input into execution. The
worked example in the appendix is an HTTP proxy sweep that produced 43 verified
RCEs across 13 builds; every rule in the body is paid for by a specific miss or
win from that work, stated here in its general form.

## Mission and definition of done

Hunt for remote code execution. RCE means attacker-influenced input causes
attacker-chosen code, or attacker-chosen structure that the target or its
ecosystem executes, to run in a process the attacker does not directly control.
The executing process may be the audited one, a component it calls, an
interpreter it drives, or a downstream service it reaches — but the trigger
travels through the target's attack surface.

**Definition of done:** at least one confirmed, reproducible RCE with a
recorded PoC and control, **or** a rigorously evidenced scoped negative stating
why no RCE exists within the declared boundary. Both outcomes require a
written report with a complete artifact index.

## Ground rules

1. Wrap every shell command in `timeout Ns`, including builds, test suites,
   fuzzers, and long-lived services. A stalled build wastes a whole session.
2. Preflight before touching a live interface: check for stale listeners or
   sockets on the interface you will use (`ss -ltnp`, `lsof -i`, the
   language's equivalent), then assert one sanity interaction before
   measuring anything.
3. Audit only the released build under test. Resolve the exact artifact
   (final release tag, deployed commit, built binary, installed package) and
   record its identity — tag, commit, source hash — before probing. Never
   audit an intermediate artifact and report it as the release.
4. Keep one running `FINDINGS.md` from minute one: every hypothesis, probe,
   result, and classification, updated in place. It is the single source of
   truth across context rollovers.
5. Persist artifacts (reports, evidence, PoC scripts, traces) in the durable
   project tree immediately, never only in `/tmp` or scrollback.
6. Classify honestly at all times: crash is not DoS is not request forgery is
   not data corruption is not RCE. Name exactly which process executes the
   code, and whether the path needs any special configuration.
7. Verify by observing the effect, never by trusting that input was sent. A
   successful return value is never sufficient; capture the executed command
   output, the executed structure (rendered template, evaluated expression,
   constructed object), or the state change the victim observed.
8. Every negative carries a forwarding control. A refusal is not evidence a
   guard fired; a broken peer or wrong endpoint also refuses. Pair every
   refusal with a harmless input that must succeed on the same path.
9. A single-trigger negative is not a family negative. Sweep the size and
   shape of a trigger, not just its presence.

## Phase 1 — Profile the target (no input yet)

1. Read the complete source. Note line numbers as you go; they go into the
   report. Identify:
   - Every **entry channel**: any path where bytes the attacker controls
     enter the target — network sockets, IPC, uploaded files, parsed
     documents, message queues, environment variables, configuration files,
     command-line arguments, dependency metadata.
   - Every **sink** each entry can reach (see the sink taxonomy below).
   - Parser structure: what is validated, in what order, and what is decoded
     or transformed **after** validation.
   - State that survives across transactions: pools, caches, sessions,
     connections, temp files, counters. Cross-transaction state is where
     desync and poisoning live.
   - Configuration: mandatory versus optional, and which knobs change the
     attack surface (delegation, plugin loading, limits, reload behavior).
2. Write the **sink inventory** in both directions before any probing:
   - Forward pass: for each attacker-controlled field, follow the value to
     every sink. This is the pass everyone does.
   - Backward pass: for each sink, enumerate every producer that can reach
     it. This is the pass that gets skipped, and the one that finds the
     second bug.
3. Write a one-paragraph attack-surface summary into `FINDINGS.md`. If you
   cannot write it, you are not done reading.
4. Build the baseline: compile or run with the language's sanitizer
   equivalents (ASan/UBSan, `_GLIBCXX_DEBUG`, Go `-race`, Python `-X dev`,
   `valgrind` where nothing native exists), run it, capture one clean
   end-to-end transaction.
5. Run one static analyzer to generate hypotheses, never to close one:

```bash
timeout 300 cppcheck --enable=warning,style,portability --inconclusive main.cpp
timeout 300 clang-tidy main.cpp -- -std=c++20
```

Swap in the language's equivalent (`go vet`, `gosec`, `bandit`, `semgrep`,
`spotbugs`, `cargo clippy`). A clean static run is not evidence of absence; a
warning is not a finding until a probe shows the effect. Record which tools
ran and their versions.

### Sink taxonomy (general)

For every entry channel, ask which of these sink classes it reaches:

| Class | What executes or what breaks | Typical families |
|---|---|---|
| **Interpreter sink** | attacker text is parsed or evaluated as code or structure by another language | shell (`sh -c`, `popen`, backticks), `eval`, SQL, template engines, regex substitution (`$1`, group refs), format strings, log substitution, deserialization (Java/Python/.NET/PHP), expression languages (OGNL, EL, SpEL, JNDI), `include`/`require`, dynamic loading |
| **Memory-shape sink** | attacker text decides how much memory to touch or how to address it | lengths, indices, offsets, allocation sizes, bounds computed from attacker input |
| **Flow-steering sink** | attacker text chooses which code path or callback runs | routing tables, dispatch maps, allowlists, callback registration, dynamic imports, classloader paths |
| **Shared-state sink** | attacker text is written into state a different transaction later consumes | caches, connection pools, session stores, shared temp files, queues, environment inherited by child processes |
| **Secondary-parser sink** | attacker text is forwarded to another parser untouched | upstream servers, protocol dispatchers, embedded interpreters, pluggable codecs |

The backward pass over this taxonomy is what finds the second bug: enumerate
every producer that reaches each sink, not just the obvious one.

## Phase 2 — Hypotheses and the escalation matrix

Write an ordered hypothesis list into `FINDINGS.md`, ranked by expected value.
Standard families, in typical hit order:

1. **Decode-then-use mismatches** — validation before decoding; decoded
   values reaching interpreter or secondary-parser sinks.
2. **Cross-transaction state desync** — pooling, caching, framing, partial
   reads, buffered leftovers.
3. **Injection into a second sink** — one value reaching two sinks where the
   first is guarded and the second is not.
4. **Cache/key collisions** — unescaped concatenation, encoding variants,
   ambiguity in the key construction.
5. **Allowlist bypasses** — anything the front door filters that a backend or
   interpreter trusts.
6. **Arithmetic and bounds** — signed/unsigned edges, near-limit accounting.
7. **Memory corruption** — only when the language and code shape allow it.
8. **Signals/reload races** — usually local-only; note, do not overclaim.

Then build the **escalation matrix** for every (entry, sink) pair, and run it
before any fuzzing. A cell describes what a primitive can reach, not whether
an input filter is strict.

### The general escalation matrix

For each (entry channel, sink) pair, test the **delimiters and metacharacters
the downstream parser treats specially**, raw and encoded, in every position
the entry admits:

| Downstream parser | Delimiters to try (raw and encoded, in-path and in-value) | Confirmed when |
|---|---|---|
| line/protocol parsers | space, tab, CR, LF, VT, FF, NUL | attacker-chosen line split, replay, or framing observed by the peer |
| shell interpreters | space, tab, newline, `;`, `\|`, `&`, backtick, `$()`, quotes, `\\`, IFS | command executes in the child shell |
| SQL | quote, backslash, comment markers, stacked-query separators | attacker-chosen statement runs |
| template / expression engines | lookup syntax (`${`, `#{`, `{{`, `%{`), class refs, method calls | attacker expression evaluates |
| paths/filesystems | `/`, `\\`, `..`, encoded separators, NUL, case folds | attacker-controlled path resolves outside the intended root |
| caches and pools | key separators, encoding variants, `\|`, newline | victim served attacker's value or state |
| regex replacement | `$` group refs, backreferences, `\\` escapes | attacker-controlled substitution injects text |
| deserializers | type markers, gadget-class names, property paths | attacker-chosen class instantiated or method invoked |

Position matters as much as content: test each delimiter in the field that
gets forwarded verbatim, the field that gets decoded then forwarded, and the
field that gets rebuilt from parts.

Rules:

1. Run every row against every candidate build, positive or previously
   negative. A build that guards row 1 usually leaks row 2; a build that
   guards rows 1–2 often leaks row 5. They are different sinks, not
   variations of one bug.
2. The matrix is per-build state, not per-family. Record
   `works` / `refused` / `echoed` per cell with the evidence filename. A cell
   left blank is an unfinished audit.
3. Every row carries the forwarding control from ground rule 8.
4. Escalating a confirmed framing or injection defect to RCE is the default,
   not extra credit. If a controlled string reaches any interpreter sink,
   that is RCE at the framing defect's severity plus one.

**The guard rule that flipped six negatives.** A guard's presence is never a
negative; only its admitted set is. A check like `c < 32` admits 0x20 (space)
and every byte above 0x7f, and space is a delimiter on the far side. State
every guard verdict as an admitted set — "rejects `c<32` and `127`,
therefore admits 0x20 and every byte above 0x7f" — never as "rejects control
bytes". Then ask what each admitted member does at each sink.

**Record delivery mode, not a binary verdict.** When a separator or
metacharacter reaches a downstream parser, record how: (1) the front end
itself splits or transforms the value, the strongest form; (2) the character
is relayed literally; (3) the character is relayed still encoded, so the
downstream must decode then split. For each build record three things: what
the guard admits, where the guard sits relative to the sink, and which string
the sink reads. A mode-3 finding must name the downstream behavior it
requires in its precondition.

## Phase 3 — Instruments

Build two harness kinds before fuzzing:

- **In-process harness**: call the parsing or decoding layer directly on
  adversarial inputs under sanitizers. Fast, exhaustive, no external service.
- **Controllable counterpart at every boundary**: a scriptable peer at each
  interface the target touches — fake upstream, mock database, stub message
  broker, `LD_PRELOAD` argv/env logger, a wrapper around `execve`, a
  filesystem diff harness. This is the workhorse of every confirmation,
  because it captures the exact bytes or calls the counterpart received,
  which is better evidence than a syscall trace for smuggling and desync
  claims.

Instrument table:

| Question | Instrument | What it answers |
|---|---|---|
| Did the decoded byte actually reach the sink? | `strace -f -e trace=execve,write,sendmsg -s 4096` (or the language's tracer: `jdb`, `pdb`, `delve`, `rr`) | the literal bytes or calls at the boundary |
| Which branch did this input take? | `gdb -p <pid>` / `jdb` / `pdb` with a command script | the decoded value and the guard test, live |
| Is the branch I think is covered actually executed? | `gcov` / `llvm-cov` / `coverage.py` / `go test -cover` | whether the vulnerable branch ran |
| Where does time go under a stall or spin? | `perf record -g` | the hot frame, not a guess |
| Is there a memory invariant break at all? | ASan/UBSan/`-race`/`valgrind` | the invariant, not which string reached which sink |

Rules:

1. Trace to confirm a primitive, not to discover one. Attach the moment a
   probe shows a suspicious asymmetry; one attachment beats twenty framing
   variations.
2. A debugger needs a reason and a bound: local process only, a command
   script, and a `timeout`. Never leave it stopped; never single-step under
   load.
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
   primitive and ask which *second* sink it also reaches: the obvious sink,
   then the rebuilt-from-parts variant, then the shared-state variant, then
   the secondary-parser variant. Every RCE in the source sweep came from this
   move, not from a new primitive. A proxy or dispatcher is an execution
   amplifier, not just a forwarder.
4. **Pass 4 — vary the precondition.** For every finding recorded with a
   precondition ("requires the URI form", "requires pipelining", "requires
   non-default config", "requires feature X enabled"), drive the other arm
   anyway. Preconditions must be tested in both arms, never inferred. This is
   what widened three narrow findings.
5. **Pass 5 — attack the premise.** When two probes in a family fail the
   same way, write the premise both assumed and test it directly instead of
   a third variation. A clean fuzz round plus a correct reframe found the
   sweep's biggest bug; a third framing variation would not have.
6. **Pass 6 — diff siblings by string source, not behavior.** When several
   targets share lineage, compare the string each sink consumes (`path`
   versus raw `target`), not their observable behavior. The one-signal diff
   separated "unreachable sink" from "reachable but unpoisoned" where
   behavioral diffs were wrong twice.
7. Repeat passes 3–5 until a full pass adds no new sink, no new admitted
   character, and no new precondition arm. Only then is the loop allowed to
   end.

Per-pass bookkeeping in `FINDINGS.md`: new sinks added, cells flipped,
preconditions widened, families reopened and closed. An interrupted pass must
never leave a verdict that contradicts its own findings table — before closing
anything, grep the verdict against the recorded cells.

## Phase 5 — Confirm, classify, report

1. A build may only be called positive from an observed execution effect:
   captured command output, an executed structure at a peer you control, a
   replayed request, an instantiated class, or a victim served from cache
   with zero new fetches.
2. Severity scale: `informational | low | medium | high | critical`. Use
   `informational`, not `info`. Framing or injection defects that execute are
   `high`; shared-state execution poisoning is `critical`.
3. The report contains: an executive summary, per-finding sections with root
   cause at `file:line` and an exact input/output example, a second impact
   demonstration where applicable, methods tried and ruled out with iteration
   counts, recommendations, and an artifact index where every cited evidence
   file exists.
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

- No probing until the hypothesis list and matrix exist.
- Fuzzing stops when a family is bounded, not when a round number is hit.
- A hypothesis that survives two well-designed probes gets one deeper look,
  then moves down the list.
- Do not close a delegating build on its own front end alone; the audit is
  not finished until the component it delegates to has been driven live with
  a counterpart you control.
- Stop a family when the sink is bounded, not when the filter is.
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

## Appendix — worked example: the HTTP proxy sweep

The method above is the generalization of a 27-run HTTP proxy sweep that
produced 43 verified RCEs across 13 builds. That sweep is the evidence base;
this appendix records how the general rules instantiated there, so a reader
can see the method applied to a concrete protocol. The corpus's own open
families — compression/TE chains, cache-key variants beyond one separator,
and vhost/alias routing — remain the next things to try on a similar target.

### Concrete escalation matrix (HTTP)

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

### Findings-table shape

One row per build, one column per family; each cell is `positive` /
`negative` / `blocked:<reason>` with an evidence file per positive. In the
source sweep the positive column totals were: request-line split 13,
body-replay desync 9, cache execution poison 5, 1xx nesting 4, `%2f` split 4,
config quoted-space 4, multi-hop chain 2, retry double-exec 2.

### Delivery-mode table from the sweep

Three delivery modes for a separator behind a prefix — the "record mode, not
yes/no" rule applied:

1. **The proxy splits the line itself** (4 tokens on the wire). Independent
   of the upstream's parsing — the strongest form.
2. **The separator is relayed literally** (a raw TAB inside the request
   line). Exploits any upstream that treats TAB as whitespace, covering
   upstreams hardened against space and CRLF.
3. **The separator is relayed still percent-encoded.** The upstream must
   decode the target then split. Weakest; needs a decode-before-split
   upstream, which the precondition must name.

Two builds are the counter-example to a naive reading of guard position:
`afdc173f` literally exempts tab (`c<32&&c!='\t'`) and still does not split
on tab, because that guard runs on the path before the split; `8d5ff1f2`
rejects tab in its decoder and relays it to the wire anyway, because the
line is rebuilt from the raw target. Guard position is part of the admitted
set: record what the guard admits, where the guard sits relative to the
split, and which string the sink reads.
