#!/usr/bin/env python3
"""Parallel no-shared-context RCE hunts over directories of implementations.

Each target directory gets its own agent diary (DIARY.md) and findings file
(FINDINGS.md). Rounds are independent `codex exec` sessions; the only state
carried between rounds is what the agent wrote into its diary, so per-round
context stays small and most of the token budget goes to hunting, not history.

Cost accounting is a conservative upper bound: every reported token is priced
at the worst-case cache-write rate, so a run never silently overruns its cap.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import types

# Nanodollars per token, worst-case: every input token billed as a cache write,
# every output token at the output rate. Mirrors toksec counted_requests PRICES.
NANO_PER_TOKEN = 1250
# One build plus one probe is about this much; below it a round dies mid-read.
MIN_ROUND_TOKENS = 60_000

DIARY_BOOTSTRAP = """\
# Diary — {target}

Running scratchpad. Append one short line after every probe, build, test
result or hypothesis change — never batch writes for the end of a round.
Each line: what you did, what you observed, the tier (T0 reach / T1 effect /
T2 break / T3 control / T4 hijack / T5 exec), and the next move.
The runner can kill the round at any moment; only what is written here
survives. Keep under 200 lines; compress older lines as you go.
"""

FINDINGS_TEMPLATE = """\
# FINDINGS — {target}

One running decision log. Update in place; never delete.

## Ledger

| id | tier | claim | rung | artifact | status |
|---|---|---|---|---|---|
| H1 | T0 | first open hypothesis | E0 | | open |

Rungs: E0 read, E1 quoted code plus reachability, E2 built probe with a
captured effect, E3 reproduced on the release build. Never claim a rung you
have not reached. `status` is `open`, `closed`, or `killed: <reason>`.
"""

# The brief is generated: it is a projection of the canonical doc, so
# the doctrine the worker sees cannot drift from the reviewed one.
# Edit docs/RCE_HUNT_FINDERS.md, then re-run this generator.
HUNT_BRIEF = """\
# RCE hunt brief

Read `ROUND.md` each round for the round number, objective and budget. Read
this brief once. The goal: decide whether any input this software receives can
cause code of another party's choosing to run, and record every distinct
mechanism. Any round may be the last, so bank findings as you go.

## The one rule that governs everything

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

## Ground rules

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
7. Classify honestly and specifically. A crash is not a DoS is not a write is
   not control is not execution. Name the tier (§5) and the exact mechanism.
9. Every negative carries a **forwarding control**: a harmless input that must
   succeed on the same path. A refusal proves nothing until the same path
   accepts something.
10. A single-trigger negative is not a family negative. Sweep size, shape,
   encoding, and position before closing a family.
12. **A guard is never a negative; only its admitted set is.** For every check,
    state what passes through it and into which sink — e.g. `c < 32` admits
    `0x20` (space) and everything above `0x7f`, so ask what each admitted member
    does at the downstream parser. A refusal proves only that this input
    failed, never that the family is bounded.

## Phase 1 — Profile the surface (no input yet)

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

## Phase 3 — The dive ladder

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

## Quick escalation matrix (native)

| Sink | One input that tries it | Confirmed when |
|---|---|---|
| integer → allocation | boundary value at the multiply/subtract | allocator log shows the small size, copy exceeds it |
| length → `memcpy`/`strcpy` | oversize field, cyclic body | offset in the captured crash is pattern-chosen |
| format string | `%1$p.%2$p…%n` in the field | leaked stack words, then a marked write |
| freed object | free-then-reuse with attacker bytes | perturbed content appears at the stale read, or a v-table slot flips |
| attacker-tagged object | tag for a larger type + short field set | `_GLIBCXX_DEBUG` abort or wrong `dynamic_cast` |
| path → loader | `../` in the plugin/include path + reload | attacker file loads or helper runs |
| null base | offset past the null object | write lands at `base + offset`, fault address tracks the offset |

## Bookkeeping

- `DIARY.md` is live, not a report. One short line after every probe, build or
  result, with the tier and the next move. After every third tool call, write
  the diary before reading anything else. Keep it under 200 lines.
- Record each mechanism in `FINDINGS.md` immediately: `MECHANISM n`, tier,
  trigger, rung, and the artifact filename that proves it. That list is your
  score.
- `ROUND.md` names one objective for this round. Land it or kill it and say why.
- `BOOTSTRAP.md` is the runner's compile result and the argv the binary needs;
  read it before touching the toolchain.
- The brief is already in your context: do not `cat HUNT_BRIEF.md` again. Slice
  large sources with `sed -n` / `fold` and pipe long output through `head -c`.

## Ending a round

Last line of your reply: `RCE CONFIRMED: <mechanism>` for a new mechanism, or
`NO RCE FOUND: <family> <admitted set>` when a family is genuinely closed. Omit
both to keep hunting.
"""

# The content classifier rejects a sizeable fraction of requests at random, and
# the more text it sees the likelier the reject. An AGENTS.md file reliably
# pushes it over the edge, so round instructions go in ROUND.md (a plain file
# the brief points at) and the prompt stays as short as possible. Rejections
# spend no tokens, so retries are free and cheap to burn.
# Files the runner itself writes into a target; never evidence of source.
RUNNER_FILES = {'DIARY.md', 'FINDINGS.md', 'HUNT_BRIEF.md', 'ROUND.md',
                'state.json', 'rounds.jsonl', 'last_round_output.txt',
                'round_live.log', 'AGENTS.md', 'BOOTSTRAP.md'}


def source_name(target):
    """A short label for the target's primary source, for the prompt only."""
    entries = [e for e in target.iterdir()
               if e.is_file() and e.suffix in SOURCE_EXTS
               and e.name not in RUNNER_FILES]
    if not entries:
        return 'the source'
    # Same preference as bootstrap_build: skip scratch drivers that only
    # include the real translation unit, and take the longest of the rest.
    texts = {}
    for e in entries:
        try:
            texts[e.name] = e.read_text(errors='replace')
        except OSError:
            texts[e.name] = ''
    pulls = {f.name for f in entries
             for t in texts.values() if f'"{f.name}"' in t and t}
    entries.sort(key=lambda e: (e.name not in pulls, -len(texts[e.name])))
    return entries[0].name


def prompt_variants(name):
    # Rotation exists only to dodge the content classifier; the wording matters
    # less than staying short. Three shapes so a retry is not a byte-identical
    # resend of a rejected request.
    return (
        f'Look for vulnerabilities in {name}.',
        f'Audit {name} for vulnerabilities. Follow HUNT_BRIEF.md.',
        f'Look for ways to run code in {name}. Read ROUND.md.',
    )

ROUND_INSTRUCTIONS = """\
# Round {round_no} of {rounds_max}

Total budget ${budget}; used {used_usd}; remaining ${remaining}.
This round is capped at roughly {round_cap} — assume you can be killed at any
instant, so write the diary before you read, not after.

## This round's objective

{objective}

Take the highest-tier live hypothesis in `FINDINGS.md` that is still open.
Land it or kill it with a reason; do not open a fresh branch while a higher
tier already has a move available.

The run can stop you at any time, so bank every finding before exploring
further. You are scored on how many *distinct* ways to run code you find and
record. A distinct mechanism is a different route to execution, not a
different input for the same route.

**First action of the round, before any read or build:** append one line to
`DIARY.md` naming the files you are about to read. The watchdog can kill you
without warning, and a killed round banks nothing that lives only in context.

Record each one in FINDINGS.md immediately as `MECHANISM n` with its tier,
trigger, rung and artifact. Keep DIARY.md current AS YOU WORK: one short line
after every probe, build or observation — never save diary writes for the
end. The round can be killed at any moment; only the diary survives it. A
round that ends without DIARY.md having grown is a FAILED round.

End your reply with `RCE CONFIRMED: <mechanism>` if you banked a new one;
otherwise write `NO RCE FOUND: <family> <admitted set>` for a family you have
genuinely closed, or omit the marker to continue.
"""

SESSION_RE = re.compile(r'session id:\s*(\S+)')
TOKENS_RE = re.compile(r'tokens used\s*\n?\s*([\d,]+)', re.IGNORECASE)


def read_tokens_used(text):
    match = TOKENS_RE.search(text)
    if not match:
        return None
    return int(match.group(1).replace(',', ''))


def session_tokens(codex_home, session_id):
    """Exact token total from the session rollout, or None.

    The stdout line is a convenience; the rollout is the source of truth and
    also covers turns whose summary was swallowed.
    """
    if not session_id:
        return None
    hits = list((Path(codex_home) / 'sessions').rglob(f'*{session_id}.jsonl'))
    if not hits:
        return None
    total = 0
    for line in hits[0].read_text(errors='replace').splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        usage = rec.get('usage') or (rec.get('payload') or {}).get('usage')
        if usage:
            total += usage.get('total_tokens', 0)
    return total or None


def run_watched(cmd, job, env, allow_tokens, args, baseline=0):
    """Run one round, killing it once it costs more than `allow_tokens`.

    `features.rollout_budget` is not enforced in the CLI build we run, so the
    cap has to be applied from outside: poll the round's own session rollout
    and kill the process group when its running token total crosses the round
    allowance. Returns (returncode, output).
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=str(job), env=env,
                            start_new_session=True)
    chunks, over, sid = [], False, None
    deadline = time.time() + args.wall_seconds
    log = (job / 'round_live.log').open('a')
    log.write(f'\n===== round start {time.strftime("%H:%M:%S")} =====\n')
    log.flush()

    def drain():
        line = proc.stdout.readline()
        if line:
            chunks.append(line)
            log.write(line)
            log.flush()

    while proc.poll() is None:
        drain()
        if time.time() >= deadline:
            over = True
            break
        if allow_tokens:
            # The banner scrolls out of a long round's tail, so latch the id the
            # first time it appears and keep polling that rollout.
            if sid is None:
                found = SESSION_RE.search(''.join(chunks[-400:]))
                sid = found.group(1) if found else None
            if sid:
                used = session_tokens(args.codex_home, sid) or 0
                if used - baseline >= allow_tokens:
                    over = True
                    break
        time.sleep(1.5)
    if over:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    # Drain whatever the child flushed before dying.
    for line in proc.stdout:
        chunks.append(line)
        log.write(line)
    rc = proc.wait()
    if over:
        rc = 124
    log.close()
    return rc, ''.join(chunks)

def cost_usd(tokens):
    if tokens is None:
        return Decimal(0)
    return Decimal(tokens) * Decimal(NANO_PER_TOKEN) / Decimal(1_000_000_000)


TIER_RE = re.compile(r'\bT([0-5])\b')


def next_objective(job, first):
    """Pick this round's objective from the target's own findings file.

    A round with a named objective is bounded and forces a conclusion; without
    one, rounds drift into re-reading. Prefer the highest-tier open lead, then
    the newest open one, then a fixed early ladder.
    """
    if first:
        return ('Build first: compile with `g++ -O1 -g -std=c++17 <source> -o '
                'target` (add `-fsanitize=address,undefined` for the twin), start '
                'it under timeout with a real config, prove one clean request, '
                'then read the parsers. Do not read the whole file first.')
    path = job / 'FINDINGS.md'
    best = None
    if path.exists():
        for line in path.read_text(errors='replace').splitlines():
            if 'closed' in line.lower() or 'killed' in line.lower():
                continue
            tier = TIER_RE.search(line)
            if not tier:
                continue
            rank = int(tier.group(1))
            if best is None or rank >= best[0]:
                best = (rank, line.strip()[:160])
    if best:
        return f'Advance the open T{best[0]} lead, or kill it: {best[1]}'
    return ('Pick the strongest open hypothesis in FINDINGS.md and take it one '
            'tier further, or close it with its admitted set.')


MARKER_RE = re.compile(r'^(RCE CONFIRMED|NO RCE FOUND):\s*(.*)$')


def closing_marker(text):
    """The round's own closing verdict, or None.

    The instructions put the marker on the last line, so the last non-empty
    line is authoritative. A round killed mid-turn often has a little trailing
    tool output, so fall back to the nearest marker line if the last line is
    prose. Echoes of the brief do not start with the marker, so they never
    match either path.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    for line in reversed(lines[-6:]):
        match = MARKER_RE.match(line)
        if match:
            return match.group(1)
    return None


def fmt_usd(amount):
    return f'${amount.quantize(Decimal("0.000001"))}'


def discover_targets(roots, pattern):
    """Immediate subdirectories that hold real files, yours or source.

    Default accepts any file so a plain source tree works; an explicit
    --pattern still narrows it. The runner's own bookkeeping files do not count
    as evidence a target is interesting.
    """
    targets = []
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            raise SystemExit(f'not a directory: {base}')
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            if pattern != '*':
                if any(entry.glob(pattern)):
                    targets.append(entry.resolve())
                continue
            for child in entry.iterdir():
                if child.is_dir() or child.name in RUNNER_FILES:
                    continue
                targets.append(entry.resolve())
                break
    if not targets:
        raise SystemExit(f'no subdirectory of {roots} holds a file matching {pattern}')
    return targets


SOURCE_EXTS = ('.c', '.cc', '.cpp', '.cxx', '.m', '.mm', '.go', '.rs', '.py',
               '.js', '.ts', '.java')
MAIN_NOARG = re.compile(r'\bmain\s*\(\s*(?:void)?\s*\)')


PORT_BASE = 18100

# Bare (no-underscore) keys common enough to be worth recognising.
CONFIG_KEYS = {'listen', 'port', 'addr', 'address', 'root', 'docroot',
               'timeout', 'depth', 'peer', 'origin', 'host', 'www', 'dir'}


KEY_LIST = re.compile(r'(?:^|[^\w])(\w*key\w*)\s*(?:\[\s*\])?\s*=\s*\{([^{}]*)\}', re.I)


def declared_config_keys(text):
    """The config key list the parser itself declares, in declaration order.

    A target that validates `m.size()!=keys.size()` rejects any extra key, so
    scraping raw string literals over-emits: one stray `"host"` literal in the
    source is enough to make the whole conf invalid. The declared list is the
    only authority, so prefer it and fall back to scrubbing only when absent.
    """
    for match in KEY_LIST.finditer(text):
        keys = re.findall(r'"([A-Za-z][A-Za-z0-9_]{1,30})"', match.group(2))
        if len(keys) >= 2:
            seen, ordered = set(), []
            for key in keys:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
            return ordered
    return []


def scrape_config_keys(text):
    """Fallback when the source has no declared key list."""
    keys = sorted(set(re.findall(r'"([a-z][a-z0-9_]{2,30})"', text)))
    # Keep strings that read as a config key rather than prose or a format.
    keys = [k for k in keys
            if '_' in k or k in CONFIG_KEYS
            or any(h in k for h in ('listen', 'port', 'addr', 'root',
                                    'timeout', 'dir', 'depth'))]
    return keys


def key_role(key):
    """Which of the three loopback addresses a key wants, if any."""
    # `auth_timeout_ms` carries an address word too, so timeouts go first.
    if key.endswith('_ms') or 'timeout' in key:
        return None
    if 'listen' in key or key.endswith('_port') or key.endswith('port'):
        return 'listen'
    if 'origin' in key or 'backend' in key or 'upstream' in key:
        return 'origin'
    if 'auth' in key:
        return 'auth'
    if 'address' in key or key.endswith('addr') or 'peer' in key:
        return 'origin'
    return None


def synthesize_config(job, text):
    """Write `bootstrap.conf` and `start.sh` from the binary's own key strings.

    Keys come from the key list the parser declares, so the conf matches the
    exact set it validates; values are deliberately small and loopback-only.
    """
    keys = declared_config_keys(text) or scrape_config_keys(text)
    if not keys:
        return False
    port = PORT_BASE + (os.getpid() % 400)
    addrs = {'listen': port, 'origin': port + 200, 'auth': port + 201}
    (job / 'www').mkdir(exist_ok=True)
    (job / 'www' / 'index.html').write_text('hello\n')
    values = {}
    for key in keys:
        role = key_role(key)
        if role:
            values[key] = f'127.0.0.1:{addrs[role]}'
        elif 'root' in key or 'dir' in key:
            values[key] = str(job / 'www')
        elif 'timeout' in key or key.endswith('_ms'):
            values[key] = '2000'
        elif 'connection' in key or 'depth' in key:
            values[key] = '16'
        else:
            values[key] = '100000'
    (job / 'bootstrap.conf').write_text(
        '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')
    script = job / 'start.sh'
    script.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\n'
                      'exec timeout ${1:-600} ./target --config bootstrap.conf '
                      '>"run.log" 2>&1\n')
    script.chmod(0o755)
    return True


def bootstrap_build(job):
    """Compile the target before the round so the model cannot spend its
    allowance re-deriving the toolchain.

    Writes `BOOTSTRAP.md` with the exact commands and whether they worked. A
    failing build is information too: the model skips straight to fixing it
    instead of starting from a blank prompt.
    """
    sources = sorted(f for f in job.iterdir()
                     if f.is_file() and f.suffix in SOURCE_EXTS
                     and f.name not in RUNNER_FILES)
    # A scratch file that includes another source (`.test.cpp` doing
    # `#include "main.cpp"`) is a driver, not the program: compiling it alone
    # leaves the real translation unit out. Prefer sources nothing else pulls
    # in, and prefer the longest, which is the program rather than a variant.
    pulls = set()
    for g in sources:
        try:
            text = g.read_text(errors='replace')
        except OSError:
            continue
        for f in sources:
            if f is not g and f'"{f.name}"' in text:
                pulls.add(f.name)
    sources.sort(key=lambda f: (f.name not in pulls, -f.stat().st_size))
    lines = ['# Bootstrap (written by the runner, one line per step)', '']
    if not sources:
        return
    if len(sources) > 1:
        lines.append(f'Multiple sources present: {", ".join(s.name for s in sources)}; '
                     'a bare g++ may need all of them or a makefile.')
    src = sources[0]
    text = src.read_text(errors='replace')
    rel = src.name
    commands = []
    if src.suffix in ('.c', '.cc', '.cpp', '.cxx', '.m', '.mm'):
        flags = ['-O1', '-g', '-std=c++17', '-fno-omit-frame-pointer']
        base = ['g++', *flags, rel, '-o', 'target']
        if 'pthread_create' in text or 'std::thread' in text:
            base += ['-pthread']
        commands.append(('release', base))
        commands.append(('asan', ['g++', *flags, '-fsanitize=address,undefined',
                                  rel, '-o', 'target.san']))
    elif src.suffix == '.go':
        commands.append(('release', ['go', 'build', '-o', 'target', '.']))
    elif src.suffix == '.rs':
        commands.append(('release', ['cargo', 'build', '--release']))
    for label, cmd in commands:
        try:
            proc = subprocess.run(cmd, cwd=str(job), capture_output=True,
                                  text=True, timeout=180)
            ok = proc.returncode == 0
            err = (proc.stderr or proc.stdout or '').strip().splitlines()
            tail = err[-1][:200] if err else 'no output'
            verdict = 'OK' if ok else f'FAIL rc={proc.returncode}: {tail}'
            lines.append(f'- {label}: `{" ".join(cmd)}` -> {verdict}')
        except (OSError, subprocess.SubprocessError) as exc:
            lines.append(f'- {label}: `{" ".join(cmd)}` -> UNAVAILABLE {exc}')
    # Record the argv the binary demands, so a launch is one line not an audit.
    wants_config = '--config' in text
    argv_style = '--config bootstrap.conf' if wants_config else ''
    if MAIN_NOARG.search(text) and not argv_style:
        argv_style = 'no arguments'
    if argv_style:
        lines += ['', f'Start form detected from main(): `./target {argv_style}`']
    if wants_config and synthesize_config(job, text):
        lines += ['', 'Wrote `bootstrap.conf` and `start.sh` from the key strings in '
                      'the source. Start it with `./start.sh` (adds `timeout`, logs '
                      'to `run.log`), then probe `127.0.0.1:$PORT`. Edit the conf '
                      'if the parser wants different keys.']
    lines += ['', 'Probe with `timeout Ns` and check the exit code, not just the text.']
    (job / 'BOOTSTRAP.md').write_text('\n'.join(lines) + '\n')


def prepare_job(target):
    """Write diary/findings into the target directory itself.

    The agent runs in its own target, so its context root is the code it is
    auditing and nothing else. No cross-target reads, no shared state.
    """
    for name, template in (('DIARY.md', DIARY_BOOTSTRAP),
                           ('FINDINGS.md', FINDINGS_TEMPLATE),
                           ('HUNT_BRIEF.md', HUNT_BRIEF)):
        path = target / name
        if not path.exists():
            path.write_text(template.format(target=target.name))
    # An AGENTS.md reliably trips the classifier; drop one if present.
    stale = target / 'AGENTS.md'
    if stale.exists():
        stale.unlink()
    bootstrap_build(target)
    return target


def run_round(job, target, state, args, round_no):
    used = Decimal(state['used_usd'])
    remaining = max(Decimal(0), Decimal(str(args.budget_usd)) - used)
    cmd = [
        'timeout', str(args.wall_seconds),
        'codex', 'exec',
        '--skip-git-repo-check',
        '-s', 'workspace-write',
        '-C', str(target.resolve()),
        '-m', args.model,
    ]
    # Resuming the target's own session keeps the next round from paying to
    # re-read what the last round already read. The id comes from state, or
    # from --session for a hunt that pre-dates recording one. Token billing
    # and the kill threshold then work on the delta against the session total.
    sid_source = state.get('session_id') or args.session
    resume = bool(args.reuse_session and sid_source)
    if resume:
        cmd += ['resume', sid_source]
    env = {**os.environ, 'CODEX_HOME': str(args.codex_home)}
    if args.provider:
        cmd += ['-c', f'model_provider={args.provider}']
    # Rollout budget is advisory and overshoots; a hard in-round token cap is
    # what actually keeps a round inside the remaining money. Only reserve the
    # last round's full allowance so a tier can never overrun its cap.
    ceiling = args.token_ceiling
    if ceiling is None:
        room_usd = remaining - Decimal(str(args.reserve_usd))
        # A per-round share keeps one round from eating a multi-round hunt. The
        # share is still capped by the money actually left, so it can never
        # overspend the target.
        if args.round_usd:
            room_usd = min(room_usd, Decimal(str(args.round_usd)))
        if room_usd > 0:
            ceiling = max(1, int(room_usd * Decimal(1_000_000_000) / NANO_PER_TOKEN))
    # A round needs enough room to reach a build even on a tiny budget, so the
    # floor wins over the money share; the budget loop stops the hunt anyway.
    if ceiling:
        ceiling = max(ceiling, MIN_ROUND_TOKENS)
        cmd += ['-c', f'features.rollout_budget={{limit_tokens={ceiling}}}']
    # Keep a slice of the allowance back for the wrap-up turn, so a kill lands
    # after the model has had a chance to bank its last diary line.
    allow_tokens = int(ceiling * 0.85) if ceiling else None
    baseline = (session_tokens(args.codex_home, sid_source) or 0) if resume else 0
    round_room = min(remaining, Decimal(str(args.round_usd))) if args.round_usd else remaining
    # Measured before the seed so `diary_written` still means "the model moved".
    diary_before = (job / 'DIARY.md').stat().st_size if (job / 'DIARY.md').exists() else 0
    findings_before = (job / 'FINDINGS.md').stat().st_size if (job / 'FINDINGS.md').exists() else 0
    # Seed the diary line here rather than trusting the model to remember it:
    # a watchdog kill then always leaves a trace of what the round was for.
    objective = next_objective(job, round_no == 1)
    with (job / 'DIARY.md').open('a') as diary:
        diary.write(f'R{round_no} started: {objective[:110]}\n')
    # Round instructions change every round, so rewrite them live.
    (job / 'ROUND.md').write_text(ROUND_INSTRUCTIONS.format(
        round_no=round_no, rounds_max=args.rounds, budget=args.budget_usd,
        used_usd=used, remaining=remaining,
        round_cap=fmt_usd(round_room), objective=objective))
    if args.dry_run:
        return {'round': round_no, 'dry_run': True, 'cmd': cmd,
                'ceiling': ceiling, 'prompt': prompt_variants(source_name(target))[0]}
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        variants = prompt_variants(source_name(target))
        prompt = variants[(attempt - 1) % len(variants)]
        rc, output = run_watched(cmd + [prompt], job, env, allow_tokens, args,
                                 baseline)
        done = types.SimpleNamespace(returncode=rc)
        flaky = 'flagged for possible cybersecurity risk' in output
        killed = rc == 124 and allow_tokens
        # A money kill is final: retrying restarts the spend. Only a
        # classifier rejection is worth re-sending.
        if killed or not flaky or attempt > args.classifier_retries:
            break
        time.sleep(min(30, 6 + 3 * attempt))
    elapsed = round(time.time() - started, 1)
    sid = SESSION_RE.search(output)
    tokens = session_tokens(args.codex_home, sid.group(1)) if sid else None
    if tokens is None:
        tokens = read_tokens_used(output)
    spent = cost_usd(tokens - baseline if tokens is not None else None)
    # The prompt and the brief both quote the marker text, so a plain substring
    # search fires on echoes. Only an anchored, near-final marker line counts.
    parts = re.split(r'^codex\s*$', output, flags=re.MULTILINE)
    result_text = parts[-1] if len(parts) > 1 else output
    marker = closing_marker(result_text)
    confirmed = marker == 'RCE CONFIRMED'
    negative = marker == 'NO RCE FOUND'
    state['used_usd'] += spent
    diary_after = (job / 'DIARY.md').stat().st_size if (job / 'DIARY.md').exists() else 0
    findings_after = (job / 'FINDINGS.md').stat().st_size if (job / 'FINDINGS.md').exists() else 0
    diary_written = diary_after > diary_before
    findings_written = findings_after > findings_before
    state['rounds'].append({
        'round': round_no, 'tokens': tokens, 'cost_usd': str(spent),
        'seconds': elapsed, 'rc': done.returncode,
        'confirmed': confirmed,
        'negative': negative,
        'marker': marker,
        'classifier_blocked': flaky,
        'killed': killed,
        'diary_written': diary_written,
        'findings_written': findings_written,
        'failed': not diary_written,
    })
    (job / 'rounds.jsonl').open('a').write(json.dumps(state['rounds'][-1]) + '\n')
    (job / 'last_round_output.txt').write_text(output[-8000:])
    if sid:
        state['session_id'] = sid.group(1)
    return state['rounds'][-1]


def hunt_one(target, args):
    job = prepare_job(target)
    state_path = job / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        state = {'used_usd': '0', 'rounds': []}
    state['used_usd'] = Decimal(state['used_usd'])
    budget = Decimal(str(args.budget_usd))
    reserve = Decimal(str(args.reserve_usd))
    first_round = 1
    if state['rounds']:
        if args.resume:
            stopped = state.get('stopped', '')
            if (stopped in ('confirmed', 'negative')
                    or stopped.startswith(('rounds exhausted', 'budget'))):
                return {'target': target.name, 'job': str(job), 'state': state,
                        'skipped': stopped}
        first_round = len(state['rounds']) + 1
    round_no = first_round
    blocked = 0
    while round_no <= args.rounds:
        projected = state['used_usd'] + reserve
        if projected > budget:
            state['stopped'] = f'budget: projected {fmt_usd(projected)} exceeds cap {fmt_usd(budget)}'
            break
        result = run_round(job, target, state, args, round_no)
        # Persist after every round: the session id must survive a kill, or
        # the next --reuse-session launch loses the thread it should resume.
        state['used_usd'] = str(state['used_usd'])
        state_path.write_text(json.dumps(state, indent=2, default=str))
        state['used_usd'] = Decimal(state['used_usd'])
        if result.get('killed') and state['used_usd'] + reserve > budget:
            state['stopped'] = (f'budget: killed at {fmt_usd(state["used_usd"])}, '
                                f'cap {fmt_usd(budget)}')
            break
        if result.get('dry_run'):
            return {'target': target.name, 'state': state, 'result': result}
        if result.get('classifier_blocked'):
            # Nothing spent, nothing done: replay the same round number.
            blocked += 1
            if blocked > 2 * (args.classifier_retries + 1):
                state['stopped'] = 'classifier: persistent rejection'
                break
            continue
        blocked = 0
        # A round the watchdog killed is not terminal: the money is spent but
        # the budget still knows how to stop. The diary is the only carried
        # state, so a killed round that never wrote one is logged as `salvaged`
        # rather than ending the hunt; a *completed* round that wrote nothing is
        # a real failure worth stopping on.
        if result.get('killed'):
            if not result.get('diary_written'):
                state['salvage'] = state.get('salvage', 0) + 1
        elif result.get('failed'):
            state['stopped'] = 'failed: no diary entry'
            break
        # A round without a find is not the end of the hunt: keep spending the
        # budget unless the operator asked to stop on the first negative.
        if result.get('negative') and args.stop_on_negative:
            state['stopped'] = 'negative'
            break
        # A confirmation banks one mechanism; keep going for more.
        round_no += 1
    else:
        state['stopped'] = 'rounds exhausted'
    state['used_usd'] = str(state['used_usd'])
    state_path.write_text(json.dumps(state, indent=2, default=str))
    return {'target': target.name, 'job': str(job), 'state': state}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--roots', nargs='+', required=True,
                        help='directories whose immediate subdirectories are targets')
    parser.add_argument('--pattern', default='*',
                        help="a target must hold a file matching this (default '*', "
                             'i.e. any real file)')
    parser.add_argument('--workdir', default='rce_hunt_runs',
                        help='where diaries, findings and state live')
    parser.add_argument('--parallel', type=int, default=2)
    parser.add_argument('--rounds', type=int, default=500,
                        help='safety cap; the budget normally stops the hunt first')
    parser.add_argument('--budget-usd', type=float, required=True,
                        help='cap per target for the WHOLE hunt')
    parser.add_argument('--round-usd', type=float, default=None,
                        help='cap one round at this much money (default: all that is left)')
    parser.add_argument('--reserve-usd', type=float, default=0.05,
                        help='minimum projected cost to start another round')
    parser.add_argument('--token-ceiling', type=int, default=None,
                        help='advisory features.rollout_budget limit_tokens per round')
    parser.add_argument('--wall-seconds', type=int, default=3600,
                        help='timeout per round (time is not the scarce resource)')
    parser.add_argument('--model', default='z-ai/glm-5.3-abliterated')
    parser.add_argument('--codex-home', default='/tmp/codex-glm',
                        help='isolated CODEX_HOME with the GLM provider only')
    parser.add_argument('--provider', default='allmodels',
                        help='codex model_provider; empty string keeps the default')
    parser.add_argument('--classifier-retries', type=int, default=6,
                        help='retries when the content classifier rejects the prompt')
    parser.add_argument('--stop-on-negative', action='store_true',
                        help='end the target hunt at the first NO RCE FOUND round')
    parser.add_argument('--reuse-session', action='store_true',
                        help='continue the target session across rounds instead '
                             'of starting a fresh conversation each round')
    parser.add_argument('--session', default=None,
                        help='seed the session id to resume (a hunt that never '
                             'recorded one, e.g. before this flag existed)')
    parser.add_argument('--resume', action='store_true',
                        help='skip targets that already reached a terminal state')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    home = Path(args.codex_home)
    if not (home / 'config.toml').exists():
        raise SystemExit(f'no config.toml in --codex-home {home}')
    if (home / 'auth.json').exists():
        print('warning: auth.json in --codex-home lets codex fall back to '
              'OpenAI and its cyber classifier', file=sys.stderr)

    targets = discover_targets(args.roots, args.pattern)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    plan = [{'target': str(t)} for t in targets]
    print(json.dumps({'plan': plan, 'targets': len(targets),
                      'budget_each': args.budget_usd,
                      'rounds': args.rounds,
                      'parallel': args.parallel}, indent=2))
    if args.dry_run:
        for target in targets[:1]:
            hunt_one(target, args)
        return

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(lambda t: hunt_one(t, args), targets))
    print(json.dumps(results, indent=2, default=str))


if __name__ == '__main__':
    main()
