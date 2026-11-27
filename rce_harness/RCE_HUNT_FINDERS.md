# RCE Finder Instructions — source to execution

**Status:** canonical instructions for any source-available RCE hunt. Every phase below is a suggestion with a
reason attached. Deviate when the target argues back, and write down why you
deviated so the next reader inherits the reasoning instead of re-deriving it.

**Audience:** an agent or operator whose task is "find remote code execution in
this software." Source is assumed available; where it is not, the black-box
variant of each phase still applies and is noted.

**Relationship:** [`toksec-next/docs/rce-finder-prompt.md`](../../toksec-next/docs/rce-finder-prompt.md)
is the HTTP/proxy-shaped specialization distilled from a 43-RCE source
sweep. It remains protocol truth; it is no longer a second general prompt.
If it conflicts here, protocol logic wins; if general hunting conflicts,
this document wins.

---

## 0. The one rule that governs everything

**Success is one working path. Breadth is how you find it.**

You are not building a proof that the target is secure or insecure. You are
looking for a single chain from attacker-controlled bytes to attacker-chosen
execution. Everything else — clean fuzzing, elegant harnesses, exhaustive
coverage, tidy write-ups — is fuel for that chain, not the deliverable.

Two consequences, and they drive the whole document:

1. **Keep many branches live at once.** A hypothesis you abandoned at 20
   minutes is worth more alive than one you polished for two hours and closed
   early. Keep a live-branch table even if an individual round works one branch
   at a time. When branches compete, rotate deliberately rather than allowing
   accidental starvation or hidden perfectionism.
2. **Harvest partials.** A symbolized crash is not an RCE, but a crash plus a
   sibling build's controllable offset is. Collect everything that moves the
   needle and keep composing.

You are explicitly invited to be creative. If a phase below does not fit the
target, cut it. The only unforgivable moves are: stopping while a branch is
still live, and reporting a claim you did not observe.

---

## 1. Mission and definition of done

**Definition of done — either arm closes the hunt:**

- **Positive arm:** one confirmed, reproducible path where attacker-influenced
  input causes attacker-chosen code, or attacker-chosen structure that a
  process the attacker does not control executes, to run. It needs a recording
  PoC, a control, and an effect captured from the execution side.
- **Negative arm:** a scoped, evidence-backed statement of why no reachable
  execution exists in the declared boundary. Every closed family needs its
  admitted set, the sink that bounded it, and the probes that bounded it. "The
  parser refused my escapes" is not a closed family; it is one probe.

The executing process may be the audited binary, a child it spawns, an
interpreter it drives, a library it `dlopen`s, or a downstream service it
reaches. The trigger still has to travel through the target's own surface. A
proxy, dispatcher, sandbox helper, or shell wrapper is an *execution amplifier*
— never close one of those because "it has no `system()` in the binary."

**Evidence rungs, in order — never claim above your rung:**

| Rung | Meaning | T3MP3ST `poc_status` |
|---|---|---|
| E0 | source read, no probe | `claimed` |
| E1 | exact code quoted, reachability traced | `source-verified` |
| E2 | targeted probe built and captures an effect | `poc-built` |
| E3 | probe re-run on R0, effect reproduced | `poc-executed` |

A T2 claim may sit at E1 while it is a lead. A **T4 or T5 claim needs E3**, or
it must say which rung it stopped at and why. T3MP3ST encodes exactly this
ladder — `scripts/verify-finding.mjs` ranks the rungs and refuses to stamp
above the declared one.

**Escalation is the default, not extra credit.** If you can put a controlled
string in front of an interpreter sink, that is RCE at the framing defect's
severity plus one. Do the arithmetic when you confirm a primitive: what is the
next tier, and what does it need?

---

## 2. Ground rules

1. `timeout Ns` on every command, always — builds, fuzzers, debuggers,
   servers. A wedged build costs the session.
2. Preflight every live interface: `ss -ltnp`, stale listeners, then one
   sanity transaction before measuring anything.
3. Pin the artifact. Resolve the exact build under test — tag, commit, source
   hash, compiler version, flags — before the first probe. Never audit a
   debug build and report it as the release.
4. **Build before auditing farther.** A hunt with no live target is still a
   read, not a hunt. Create a release or near-release artifact, start it with
   its real inputs or peers under `timeout`, prove one clean interaction, then
   create the sanitized twin. Sandbox blocks become *harness work*, not a reason
   to spend rounds on static re-reading.
   **Read in slices, not sweeps.** A minified file dumped whole is 40k tokens of
   context that can be killed before it is used. `fold -s -w 160 | nl | sed -n`
   one 200-line window at a time, and write the diary line naming what you read
   before reading it. Nine silent reads and no diary is a round that banked
   nothing.
5. One running `FINDINGS.md` from minute one: every hypothesis, every probe,
   every result, every classification, updated in place. It survives context
   rollover and it is where the report comes from.
6. Artifacts go to the durable tree immediately — never only `/tmp`, never
   only scrollback.
7. Classify honestly and specifically. A crash is not a DoS is not a write is
   not control is not execution. Name the tier (§5) and the exact mechanism.
8. **Verify by effect, never by "input was sent."** Capture the executed
   command's output, the corrupted register, the peer's received bytes, the
   served-victim state. A `200`, a non-zero exit, or a log line is never proof
   on its own.
   **Check the probe's exit code before its text.** `curl_rc=7` with a "200 OK"
   in the note means nothing ran; the server never came up. Record the exact
   start command that worked (`./target --config conf`, not `./target`) beside
   the probe, so a failed launch is visible as a failed launch. A probe rung is
   only E2 once the artifact shows both a working launch and the effect.
9. Every negative carries a **forwarding control**: a harmless input that must
   succeed on the same path. A refusal proves nothing until the same path
   accepts something.
10. A single-trigger negative is not a family negative. Sweep size, shape,
   encoding, and position before closing a family.
11. When two probes in one family fail identically, stop adding a third.
    Write the premise both assumed and attack *that*.

12. **A guard is never a negative; only its admitted set is.** For every check,
    state what passes through it and into which sink — e.g. `c < 32` admits
    `0x20` (space) and everything above `0x7f`, so ask what each admitted member
    does at the downstream parser. A refusal proves only that this input
    failed, never that the family is bounded.

---

## 3. Phase 1 — Profile the surface (no input yet)

Read the source completely, in the order a parser runs, not the order files
sit in the tree. Note line numbers as you read; they become the report.

Build four lists before probing:

0. **A live process, before the lists are finished.** Build the target from
   its own instructions, start it under `timeout` with real inputs or a peer,
   and prove one clean interaction. Only then continue reading. If the sandbox
   blocks a syscall, probe what *is* allowed and record the shim you need —
   that is harness work, and it is yours.
1. **Entry channels** — every place attacker bytes enter: sockets, IPC,
   `argv`/`envp`, config and dotfiles, uploaded or parsed documents, archive
   members, message queues, socket options, metadata, plugin manifests,
   `LD_*`, file paths, symlinks, terminal escapes, environment inherited by
   children.
2. **Sinks** — forward and backward. The forward pass (field → sink) is the
   one everyone does. The **backward pass** (sink → every producer that can
   reach it) is the one that finds the second bug and it is not optional here.
3. **Decode-after-validate order** — what is checked, where decoding happens,
   and which transformed value reaches the sink. Validation before decoding
   is the canonical C++ trap (`strlen` on the encoded form, `strtol` on a
   re-encoded copy, `%` handling before unescape).
4. **Lifetime and size state** — ownership, `unique_ptr`/`shared_ptr` graphs,
   `std::string_view` and `span` aliasing, arena lifetimes, `reserve`,
   `resize` vs `reserve` confusion, iterator invalidation, `data()` caches.

Also record, because it changes the attack surface: build flags (`-O3
-DNDEBUG` strips `assert`), stack protector, FORTIFY, RELRO/PIE, whether the
target `dlopen`s, spawns children, `chroot`s, or drops privileges.

Then, still without probing:

- Compile a **sanitized twin** (`-fsanitize=address,undefined -fno-omit-frame-pointer
  -g -O1`) and a **debug twin** (`-g -O0`). These are separate from the release
  artifact and never get reported as it.
- Generate hypotheses from one static analyzer — `cppcheck`, `clang-tidy`,
  `infer`, `semgrep` — and treat output as leads, not findings.
- Write the one-paragraph surface summary into `FINDINGS.md`. If you cannot,
  the read is not done.

### Extended sink taxonomy

The generic taxonomy (interpreter, memory-shape, flow-steering, shared-state,
secondary-parser) still applies. For native targets add these, because they
are where C++ bugs actually live:

| Class | What breaks | Where to look |
|---|---|---|
| **Length/width arithmetic** | a computed size disagrees with the buffer it describes | `size_t` underflow, `int`→`size_t` sign flip, `a*b` without overflow check, `-1` as sentinel for `npos`, `snprintf` return used as a count |
| **Ownership confusion** | the wrong code frees, or two owners free | double free, use-after-free, `unique_ptr` released then used, callback holding a raw pointer past lifetime |
| **Aliasing** | one buffer read as two types or two lengths | `reinterpret_cast`, `memcpy` with mismatched `sizeof`, union punning, struct-over-buffer cast |
| **Iterator/container invalidation** | a reference survives a mutation | `push_back` during iteration, `erase` in a loop, `string_view` into a `std::string` that reallocates |
| **Format-string** | attacker text is the format | user string passed to `printf`/`snprintf`/`syslog`; `%n` is a write primitive |
| **Type confusion** | a v-table or tag disagrees with the storage | craft-serialized objects, `dynamic_cast` on attacker-tagged data, variant index out of range |
| **Null-deref escalation** | a `NULL` page maps, or an offset from a null base is another object | `memcpy` to offset-from-null, null `this` with a virtual call |
| **Path/recursion bombs** | unbounded depth or quadratic work | recursive descent parsers, self-referential archive members, decompression ratio |

---

## 4. Phase 2 — Hypothesis portfolio and the build ladder

Write an ordered hypothesis list into `FINDINGS.md`, ranked by expected yield.

The portfolio and the round are different scopes, and both rules hold:

- **The portfolio stays wide.** Three or more branches live at all times until
  one closes the hunt. Narrowing to a single theory is how a hunt dies with the
  wrong answer.
- **The round stays single-minded.** One round works one named objective,
  normally the highest-tier open branch, taken one tier further or killed with
  a reason. Do not open a fresh branch while a higher tier already has a move.
- **Branches earn their slot or lose it.** A branch with no move in a while is
  not "still open": give it one explicit decision — advance, or kill with a
  stated reason — and open the next from the yield order.

So the objective in `ROUND.md` is the branch this round spends money on, not a
vote to abandon the rest. When it closes, the next round takes the
highest-ranked branch still live.

Typical yield order for native targets (adapt to the read):

1. Parse-then-use mismatch on a length or index.
2. Unbounded / unchecked copy into a fixed buffer or a wrongly-sized alloc.
3. Integer arithmetic feeding an allocation or an index.
4. Ownership/lifetime bug on a session or per-request object.
5. Format string or log-injection sink reached by user text.
6. Deserializer / tag confusion / v-table confusion.
7. Path traversal into a `dlopen`, `exec`, or config reload.
8. Null-deref with a controllable offset.

Then build the **ladder of target builds**, one per rung, and keep them all
available — the same source at increasing observability:

| Rung | Build | Purpose |
|---|---|---|
| R0 | release, as shipped (`-O3 -DNDEBUG`) | truth; nothing else substitutes |
| R1 | `-O1 -g -fno-omit-frame-pointer` | symbolized crashes, honest stack |
| R2 | R1 + ASan/UBSan | invariant break, redzone, UAF |
| R3 | R2 + `_GLIBCXX_DEBUG` / `-D_GLIBCXX_ASSERTIONS` | container and iterator abuse |
| R4 | R1 + a **canary harness**: `MALLOC_PERTURB_`, an `LD_PRELOAD` logging `malloc`/`free`/`memcpy`/`strcpy`, or a guarded allocator | which copy, which size, which owner |

R4 is the workhorse for turning a vague crash into a mechanism. `MALLOC_PERTURB_=170`
makes freed memory visibly different from fresh memory; an `LD_PRELOAD` of
`memcpy`/`strncpy` with an argument log tells you the exact length the target
passed. Both are cheaper and more diagnostic than a debugger for length bugs.

**Run the same input against all rungs.** Divergence between R0 and R2 is a
finding; identical behavior is a lead you can drop.

---

## 5. Phase 3 — The dive ladder

This is the spine. Each tier is a question you answer with an observation,
and each tier has a **dovetail** — the adjacent question that a success opens.
You do not have to enter at tier 0 every time; a source-derived offset can
start you at tier 3.

| Tier | Question | Confirmed by | Dovetail |
|---|---|---|---|
| **T0 Reach** | Can attacker bytes reach the code at all? | a probe whose effect reaches the function (log, breakpoint hit, divergent return) | Which *neighbouring* entry reaches the same function with more room? |
| **T1 Effect** | Does the value do anything observable? | reflection, wrong length, dropped record, timing delta | Is the effect a *read* (leak) or a *write* (corruption)? |
| **T2 Break** | Does a size/lifetime/type invariant break? | ASan/UBSan report, `_GLIBCXX_DEBUG` abort, `MALLOC_PERTURB_` garbage surfacing | Which byte, and which offset, first touched the broken thing? |
| **T3 Control** | Are the corrupting bytes attacker-chosen at a chosen offset? | a `cyclic 2000` pattern (pwntools, or any de-Bruijn generator) in a captured crash, `%n` writing a known value, an allocator log showing the chosen length | Does the same length formula let you move the offset to a target field? |
| **T4 Hijack** | Does control reach something executable? | an overwritten return address, function pointer, v-table slot, or `__free_hook`/GOT entry, shown in the crash | Which register or slot, and is it a call or a jump? |
| **T5 Exec** | Does chosen code run? | `execve("/bin/sh")`, a `/bin/cat $FLAG` marker in stdout, a bound shell, or a compiled `system()` returning command output | Reproducibility on R0, then the clean PoC |

Tier discipline:

- **Never skip T0.** A beautiful T5 chain on an unreachable function is a
  local bug, not an RCE.
- **Record the tier in every finding.** "Crash" is T2. Say T2.
- **A T2 with a *controllable* offset is worth more than a T1 with a pretty
  leak.** When two branches stall, prefer the one nearer T3.
- **When a branch stalls at tier N, do not retry it.** Move to the dovetail
  of the branch nearest its own tier, and log the stall.

Deliverable per confirmed tier: an evidence file plus one sentence naming the
mechanism. `f_0001_T3.log: cyclic 2000, rc offset 264, attacker-chosen` beats
a paragraph of prose.

---

## 6. Phase 4 — Parallel branches and differential work

Breadth is a technique, not a mood. Run structurally different branches
concurrently and let them cross-pollinate:

- **Forward** from a known entry, and **backward** from a known sink.
- **Same-input, different-rung** differentials (R0 vs R2) — cheap, and one
  divergence pays for the batch.
- **Sibling diff by string source, not behavior.** For lineage builds, compare
  the string each sink consumes, not the observable output. Behavioral diffs
  lied twice in the source sweep; the signal is upstream of behavior.
- **Config-arm pairs.** Every finding recorded with a precondition gets the
  other arm driven too. Preconditions are tested, never inferred.
- **Fixed-vs-relocatable probes.** The same input at a different load address
  or with a different heap shape separates "logic bug" from "address luck."
- **Structure-aware fuzzing** on any parser, with a seeded corpus of valid
  inputs — and coverage (`llvm-cov`, `gcov`) so you know what actually ran.

Fuzzing is a *bounded* instrument. It proves memory-safety presence well and
logic bugs badly. A clean 50k-iteration run licenses "no memory-safety bug at N
iterations, C% coverage" — it does not license "no RCE." If fuzzing comes back
clean, go back to §4 and attack the premise.

Branch hygiene: a live-branch table in `FINDINGS.md` with tier, owner,
last-move, and kill criterion. A branch with no move in a while gets one
explicit decision — advance, or kill with a reason.

---

## 7. Phase 5 — Escalation recipes (C++ specializations)

Pick by shape. Each recipe names its own precondition; test the precondition
both arms.

**Fixed-buffer copy / `strcpy`/`sprintf`/`memcpy` with a computed length.**
Find the formula. Substitute the overflow for a controlled write: `MALLOC_PERTURB_`
plus a cyclic pattern shows the offset. Then pick the target — return address,
saved frame pointer, function pointer in the adjacent struct, or a C++
v-table slot if the object is polymorphic and you can reach the constructor
with oversize input.

**Format string.** `printf(user)` / `syslog(prio, user)` / a logging shim that
forwards `%s`-less text. Walk `%1$p`, `%2$p`, … to index a controlled buffer
into an argument slot, then `%n` at the marked word. `%n` needs a writable
target and a pointer in the argument window — usually a stack address you
leaked with `%p`.

**Integer arithmetic into allocation or index.** `size_t n = a * b` or `n = a - b`.
Drive `a*b` past `SIZE_MAX` so the allocation shrinks and the copy overruns,
or drive `a-b` negative so the index reads before the base. `strtoul` and
`atoi` are where the sign flips hide.

**Use-after-free / ownership.** A request object, session, cache node, or
callback outliving its owner. `MALLOC_PERTURB_` makes the reuse visible; a
`LD_PRELOAD` free logger names the sequence. Reallocate the freed slot with
attacker bytes, then trigger the stale read to reach a v-table or function
pointer in the new contents.

**Type / tag confusion.** A serialized object whose tag is attacker-chosen.
Give it a tag for a larger or more privileged type, then feed fields sized for
the smaller one. A wrong `dynamic_cast` result or an out-of-range variant index
is the tell.

**Path into `dlopen`/`exec`/reload.** Path traversal or symlink followed into a
plugin search directory, a config `include`, a `SIGHUP` reload, or a helper
spawn. Traversal plus a writable directory plus a reload is often a direct T5
without any memory corruption.

**Null base + controlled offset.** A null `this`, null global, or null
container base with an attacker offset. A mapped zero page or a controlled
allocation at a low address turns the offset into an arbitrary write against
the null base.

Confirm every step with the effect, not the theory: the register value, the
captured `peer_up` bytes, the allocator log line, the `uid=` on stdout.

---

## 8. Phase 6 — Other target classes

The ladder is language-neutral; the recipes change.

- **Rust:** start from `unsafe`, `from_raw_parts`, `transmute`,
  `set_len`, FFI boundaries, and `*mut` in `std` interop. `-Z sanitizer` on
  nightly, or `cargo +nightly miri` for UB-shaped bugs. Panics are T2.
- **Go:** `unsafe.Pointer`, `cgo` boundaries, `slice[a:b]` with `b<a`, `defer`
  ordering under panic, `sync.Pool` reuse. `-race` and `GOGC` pressure.
- **Python/JS/other managed:** `ctypes`/`cffi`, native extensions, `eval`/`exec`,
  template engines, `pickle`/`marshal`, regex engines, `subprocess` without
  `shell=False`, deserialization gadget chains. The RCE is in the native or
  interpreter seam, not the managed core.
- **Binary protocol / state machine (e.g. an SSH or RDP handshake):** treat
  each handshake step as an entry channel and each parse as a sink. Sizes,
  algorithms, and string lengths negotiated early are attacker-chosen long
  before they reach a copy. The custom transport servers in the sweep's probe
  summary are exactly this shape.
- **Document / archive / image parsers:** recursion depth, member counts,
  decompression ratio, embedded offsets, and the decoder that runs *after*
  validation.

---

## 9. Phase 7 — Confirm, classify, report

1. A finding is positive only from an observed execution effect captured on
   the execution side — command output, a spawned shell, a served victim, an
   instantiated class at a peer you control.
2. **Re-run the winning chain three times on R0**, under `timeout`, from a cold
   start. A flaky chain is T4 at best.
3. Severity: `informational | low | medium | high | critical`. Uncontrolled
   crashes are `informational`/`low`. Controlled write to a reachable pointer
   is `high`. Attacker-chosen execution is `critical`.
4. The report: executive summary, per-finding root cause at `file:line` with an
   exact input and output, a second impact demonstration where it exists,
   methods tried and ruled out with iteration counts, recommendations, and an
   artifact index where every cited file exists.
5. Give the RCE verdict its own line, even when negative: "no remote code
   execution within scope, because X." Never let "no memory-safety finding"
   stand in for it.
6. State the required configuration in the body and the findings table.
   "Requires `-O0`" or "requires the plugin path writable" belongs in the
   result, not a footnote.
7. Mark every claim **mechanically verified** (hash, capture, re-run) or
   **author-attested** (method, environment). Never present a reconstruction as
   run-time provenance.

Publishing into a repo with its own workflow follows that repo's rules — read
its `AGENTS.md` and result-storage docs first, and use its recording tool over
direct placement. In `toksec`/`toksec-next` that is
`scripts/record_security_evaluation.py` then `scripts/publish_results.py`, with
envelopes append-only and `scripts/lint_security_reports.py` as the gate.

### T3MP3ST machinery that already enforces this document

Use these rather than re-deriving them; each one turns a rule above into a
mechanical check.

| Need | Use | What it enforces |
|---|---|---|
| claim rung | `scripts/verify-finding.mjs` | E0-E3 ladder; refuses to stamp above the declared rung |
| code really exists | `verify-finding.mjs` anchors (`file:line` + `must_contain`) | rejects asserted or paraphrased code |
| guard actually dominates | `verify-finding.mjs` dominating-guard scan | demotes a memory claim with an unchecked bound above the sink |
| adversarial refutation | `scripts/refute-finding.mjs` | kill-first skeptics, majority-refute wins |
| control before grading | `rce_matrix/poc/row.py` (`control failed: ...`) | no cell scores until a benign control returns 200 |
| findings shape | `rce_matrix/SUMMARY.md` / `cells.json` | one column per family, `positive`/`negative`/`blocked:<reason>` |
| breadth on large repos | `scripts/cli-swarm.mjs` | parallel lenses plus a refuting skeptic |

`rce_matrix/poc/README.md` is the reference for proof style: upstream-side
evidence only, a control before every cell. Fan-out and fuzzing earned little
on single dense files, so reserve `cli-swarm` for repos wide enough to deserve
it.

---

## 10. Stopping rules and timeboxing

- No probing until the hypothesis list and the surface summary exist.
- Fuzz until the family is *bounded*, not until a round number.
- A hypothesis that survives two well-designed probes gets one deeper look,
  then moves down the list.
- Never close a delegating target on its front end alone; drive the component
  it delegates to with a counterpart you control.
- Stop a family when the **sink** is bounded, not when the **filter** is.
- Only stop the hunt when: a chain is confirmed on R0, or every live branch is
  killed with a written reason, its **admitted set** is recorded, and the
  strongest partials are documented.
- **Do not emit "no RCE" while a branch is live.** Name the branch and what it
  still needs.
- **A hunt with no live process is not finished.** If the target never ran, say
  so in the verdict and name the build or sandbox step that is blocking it.

A worked persistence floor is in `docs/COGNITIVE_ARCHITECTURE.md` §v4.2 — the
harness rejects `FLAG: UNKNOWN` before iteration 20. This playbook's version is
the live-branch table: no verdict while a branch has an open move.

---

## 11. Anti-patterns that cost real time

| Anti-pattern | Cost | Instead |
|---|---|---|
| Fuzzing first, reading never | 11k clean cases found nothing in the sweep; reading found it | read, then fuzz to bound |
| Trusting the guard instead of its admitted set | a `c<32` check published as "control bytes handled" while `0x20` sailed through | write the admitted set: "rejects <0x20 and 0x7f, therefore admits 0x20 and ≥0x80" |
| Debugger without a reason | stalls, no evidence | attach only when a probe shows asymmetry; use a command script |
| Reporting a crash as RCE | overclaim | name the tier |
| One branch, polished | low yield | three live branches, all timestamped |
| `assert`-bearing build reported as release | wrong artifact | audit R0, symbolize with R1+ |
| Closing on a single trigger | false negative | sweep size and shape |
| "The request was sent" | unproven | capture the effect |
| A clean fuzz round as the conclusion | bounds only memory safety | it licenses a scoped statement, nothing more |
| Static-only rounds on an unstarted binary | the sweep found nothing without a running peer | build, start, prove one interaction, then read on |
| Re-printing the same source under a new formatter | cost a whole budget round in the $7 run | one `sed`/`rg` over the exact range; read once |
| Guessing the sandbox limit instead of probing it | a round burnt inventing a `socketpair` shim | probe which syscalls work, record it, then harness |

---

## 12. Quick escalation matrix (native)

| Sink | One input that tries it | Confirmed when |
|---|---|---|
| integer → allocation | boundary value at the multiply/subtract | allocator log shows the small size, copy exceeds it |
| length → `memcpy`/`strcpy` | oversize field, cyclic body | offset in the captured crash is pattern-chosen |
| format string | `%1$p.%2$p…%n` in the field | leaked stack words, then a marked write |
| freed object | free-then-reuse with attacker bytes | perturbed content appears at the stale read, or a v-table slot flips |
| attacker-tagged object | tag for a larger type + short field set | `_GLIBCXX_DEBUG` abort or wrong `dynamic_cast` |
| path → loader | `../` in the plugin/include path + reload | attacker file loads or helper runs |
| null base | offset past the null object | write lands at `base + offset`, fault address tracks the offset |

---

## 13. Return value

At the end of a hunt, hand back three things:

1. The `FINDINGS.md` narrative with the tier per finding and every stall named.
2. The PoC plus control for each confirmed tier, on R0.
3. The one-line verdict: a chain to execution, or "none within scope, because
   X," with the branches that were killed and why.

If a branch is still live, the verdict ends with what it needs and where you
left it. The next reader should be able to resume from that line in under a
minute.

---

## 14. Parallel fan-out runner

`scripts/rce_fanout.py` turns a directory of implementation folders into
isolated, parallel hunts. Every target is its own `codex exec` session with no
shared context: the only state carried between rounds is `DIARY.md` and
`FINDINGS.md`, written inside the target itself. The brief lives in
`HUNT_BRIEF.md`; the per-round prompt stays short so most tokens go to the
audit, not to restating history.

```bash
# all targets under rce_matrix/, $2 cap each, up to 4 rounds, 2 at a time
python3 scripts/rce_fanout.py --roots rce_matrix --budget-usd 2 \
  --parallel 2 --rounds 4

# later: skip targets that already finished confirmed/negative/exhausted
python3 scripts/rce_fanout.py --roots rce_matrix --budget-usd 4 \
  --parallel 2 --rounds 8 --resume
```

Key flags:

| Flag | Meaning |
|---|---|
| `--roots` | directories whose immediate subdirs are targets |
| `--pattern` | a subdir qualifies if it contains a file matching this (default `*.md`) |
| `--budget-usd` | hard cap per target across all rounds |
| `--reserve-usd` | don't start a round unless projected cost fits |
| `--token-ceiling` | per-round token allowance; derived from the remaining budget when omitted |
| `--stop-on-negative` | end the target at the first `NO RCE FOUND` (default: keep hunting) |
| `--wall-seconds` | timeout per round (default 900) |
| `--resume` | skip confirmed, negative and budget-exhausted targets |

A round is killed from outside once its live token total reaches 85% of its
allowance, because `features.rollout_budget` is not enforced by the CLI build.
The kill lands after the wrap-up slice, so the diary normally closes first; a
killed round still advances rather than failing, and its `state.json` records
`killed: true`. Timeouts and money kills both surface as `rc 124`.

Cost accounting is deliberately conservative: every reported token is priced at
the worst-case cache-write rate (1250 nanodollars/token), so a hunt never
silently overruns its cap. Round output streams to the target's
`round_live.log` while it runs; the tail also lands in `last_round_output.txt`.

`/tmp` here is a tmpfs capped at 1,048,576 inodes, not at its byte size. Long
lived scratch work fills the inode table while `df -h` still reports space, and
then `codex` fails to mount its sandbox. Check `df -i /tmp` before a long
campaign and prune stale `leo-*` scratch dirs; inode exhaustion is the failure
mode to watch, not bytes.

Round results land in each target's `state.json`,
`rounds.jsonl`, and `last_round_output.txt`; stop reasons are `confirmed`,
`negative`, `budget: ...`, `failed: no diary entry`, or `rounds exhausted`.

Note: `codex exec` needs an escalated sandbox (it writes under `~/.codex`), and
the content classifier intermittently rejects cyber-worded prompts; the runner
retries the same prompt with backoff (`--classifier-retries`, default 6).
If a round is killed by the wall timeout or budget guard, no tokens are
reported by `codex exec` and the round is booked at cost zero while the stop
reason records the failure — a run may spend slightly less than the parsed
total suggests, never more.
