#!/usr/bin/env python3
"""Render the in-target HUNT_BRIEF.md from docs/RCE_HUNT_FINDERS.md.

The brief is not a summary written by hand: it is a projection of the canonical
document's load-bearing sections, so the doctrine the worker sees cannot drift
from the doctrine that was reviewed. `--check` fails when the file committed in
scripts/rce_fanout.py no longer matches the document.

Usage:
  python3 scripts/gen_hunt_brief.py          # rewrite the string in place
  python3 scripts/gen_hunt_brief.py --check  # verify, exit 1 on drift
"""
import argparse
import pathlib
import re
import sys

DOC = pathlib.Path(__file__).resolve().parent / 'RCE_HUNT_FINDERS.md'
RUNNER = pathlib.Path(__file__).resolve().parent / 'rce_fanout.py'

# Sections of the canonical doc that survive into the brief, in brief order.
SECTIONS = ('0', '2', '3', '5', '12')

PREAMBLE = """# RCE hunt brief

Read `ROUND.md` each round for the round number, objective and budget. Read
this brief once. The goal: decide whether any input this software receives can
cause code of another party's choosing to run, and record every distinct
mechanism. Any round may be the last, so bank findings as you go.
"""

TAIL = """## Bookkeeping

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

HEADING_RE = re.compile(r'^## (\d+)\.(.*)$', re.MULTILINE)


def extract(text):
    """Pull the named sections out of the canonical document."""
    marks = list(HEADING_RE.finditer(text))
    out = {}
    for idx, match in enumerate(marks):
        end = marks[idx + 1].start() if idx + 1 < len(marks) else len(text)
        body = text[match.end():end]
        body = re.split(r'^---\s*$', body, flags=re.MULTILINE)[0].strip()
        out[match.group(1)] = (match.group(2).strip(), body)
    return out


KEEP_RULES = {
    # §2: the rules a worker can actually violate in one round.
    '2': ('3', '4', '5', '7', '9', '10', '12'),
    # §3: the four lists and the build ladder, without the prose around them.
    '3': ('0', '1', '2', '3', '4'),
}


def trim(number, body):
    """Keep only the listed numbered items of a section, when asked to."""
    wanted = KEEP_RULES.get(number)
    if not wanted:
        return body
    items, current = {}, None
    for line in body.splitlines():
        head = re.match(r'^(\d+)\.', line)
        if head:
            current = head.group(1)
            items[current] = [line]
        elif current and line[:1] in (' ', '\t'):
            # Wrapped continuation only; unindented prose starts a new thought.
            items[current].append(line)
        elif current:
            current = None
    kept = [items[n] for n in wanted if n in items]
    return '\n'.join('\n'.join(chunk) for chunk in kept)


def render(doc_text):
    parts = [PREAMBLE]
    sections = extract(doc_text)
    for number in SECTIONS:
        if number not in sections:
            raise SystemExit(f'section {number} missing from {DOC.name}')
        title, body = sections[number]
        parts.append(f'## {title}\n\n{trim(number, body)}\n')
    parts.append(TAIL)
    brief = '\n'.join(parts)
    # Tiers are referenced throughout the brief, so they stay in it verbatim
    # from §5's table; nothing else about the doc is copied.
    return brief


HEADER = ('# The brief is generated: it is a projection of the canonical doc, so\n'
          '# the doctrine the worker sees cannot drift from the reviewed one.\n'
          '# Edit docs/RCE_HUNT_FINDERS.md, then re-run this generator.\n')


def replace_in_runner(source, brief):
    start = source.index('HUNT_BRIEF = """\\')
    # Consume the comment block above the assignment so re-runs stay identical.
    while True:
        line_start = source.rfind('\n', 0, start - 1) + 1
        if not source[line_start:start].lstrip().startswith('#'):
            break
        start = line_start
    end = source.index('# The content classifier rejects')
    block = HEADER + 'HUNT_BRIEF = """\\\n' + brief + '"""\n\n'
    return source[:start] + block + source[end:]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    doc_text = DOC.read_text()
    brief = render(doc_text)
    source = RUNNER.read_text()
    updated = replace_in_runner(source, brief)
    if args.check:
        if updated != source:
            print(f'{RUNNER.name} brief is stale; run {pathlib.Path(__file__).name}',
                  file=sys.stderr)
            return 1
        print('brief in sync')
        return 0
    RUNNER.write_text(updated)
    print(f'rewrote HUNT_BRIEF in {RUNNER.name} ({len(brief.splitlines())} lines)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
