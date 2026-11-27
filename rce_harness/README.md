# RCE harness

A standalone, per-target RCE hunt driver. It runs independent `codex exec`
rounds over a directory of implementations, one target per subdirectory, so no
round inherits another round's context. The only state carried between rounds is
what the agent wrote into its own `DIARY.md` and `FINDINGS.md`.

This is not the toksec measurement path. Nothing here consumes a stage contract
or writes under `results/`; it produces hunt transcripts you can read, cite and
harvest PoCs from.

## Files

| File | Purpose |
|---|---|
| `rce_fanout.py` | The runner: target discovery, per-round budget cap, token watchdog, verdict parsing |
| `RCE_HUNT_FINDERS.md` | The canonical doctrine, including tiers T0–T5, evidence rungs E0–E3 and the negative arm |
| `gen_hunt_brief.py` | Renders the in-target `HUNT_BRIEF.md` from that document; `--check` fails on drift |
| `test-rce-fanout.mjs` | Pins the round-verdict contract and the doc/brief sync |

The brief the worker reads is a projection of the document, so review the
document, not the brief. Edit `RCE_HUNT_FINDERS.md`, then re-run
`python3 rce_harness/gen_hunt_brief.py`.

## Usage

```sh
python3 rce_harness/rce_fanout.py --roots ./targets --budget-usd 2.00 --round-usd 0.20
```

Each subdirectory of `--roots` is one target. The runner writes `DIARY.md`,
`FINDINGS.md`, `ROUND.md`, `BOOTSTRAP.md`, `state.json` and `rounds.jsonl` into
it, compiles the target before the first round, and puts the compile result and
the argv `main()` needs in `BOOTSTRAP.md`. When the source takes `--config` it
also writes a loopback `bootstrap.conf` and a `start.sh` around it.

Cost is a conservative upper bound: every reported token is priced at the
worst-case cache-write rate, so a run will not silently overrun its cap. The
round cap is clamped by the money left, and the watchdog kills a round that
crosses its token allowance.

Relevant flags:

- `--round-usd` — per-round cap, clamped by the remaining budget
- `--stop-on-negative` — end a target at its first `NO RCE FOUND` (default: keep spending)
- `--resume` — skip targets already in a terminal state
- `--wall-seconds` — per-round wall clock, default 3600
- `--dry-run` — show the plan and one round's command without spending

## Verdict contract

A round ends with `RCE CONFIRMED: <mechanism>` or
`NO RCE FOUND: <family> <admitted set>` on its last non-empty line. The prompt
and the brief both quote those markers, so an echo is not a verdict; only an
anchored final line counts, and the nearest marker is used when a killed round
leaves trailing tool output.

## Tests

```sh
node rce_harness/test-rce-fanout.mjs
python3 -m unittest discover -s tests
```
