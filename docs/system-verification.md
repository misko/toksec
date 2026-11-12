# Verification record

Verified on 2026-11-12 UTC. No new paid inference was used for this change.

## Reproduce

```sh
python3 -m toksec publish --output tasks/v2
python3 -m unittest discover -s tests -v
```

The final full run passed 56 tests in 35.482 seconds on this host. The suite covers both the preserved Python pilot and the new Rust system.

| Area | Observed evidence |
|---|---|
| Contracts | All five generated Markdown/JSON packets agree with executable definitions. Levels contain 11/16/20/24/30 public checks and 4/8/8/12/20 benchmark workloads. |
| Compiler | Real Rust sources compile and run inside Bubblewrap. A compile-time include of the host credential path fails. |
| Runtime | A compiled Rust fixture serves requests in its private network namespace and cannot see the host credential path or API-key environment variable. |
| Level 5 linking | Sandboxed Rust unit tests link and call the approved OpenSSL and zlib libraries. This verifies library availability, not a generated TLS server. |
| Public evaluation | A deliberately incomplete Rust server fails the suite. A working partial is retained; a later uncompilable candidate cannot replace it. |
| Deadline | Interruption during submission retains the prior artifact. |
| Load generator | Real sandboxed Rust processes exercise both 256 and 4096 client loops. Attempts equal successes plus failures. Counted payload bytes equal valid completions times body size. |
| Bad responses | An incorrect server produces failures and zero valid goodput. |
| Accounting | Imported pilot cost, cross-run reservations, both spending ceilings, duplicate settlement, incorrect service tier and unresolved responses are tested. |
| Tool loop | A fake API backend drives real sandbox compilation and evaluation. It confirms standard tier, public-suite inclusion, archived candidates and accounting. No simulated usage is written into the live campaign. |
| CLI | All five independent runs prepare and pass local preflight. Their candidate directories remain empty. The exported public-suite package compiles and runs a Rust unit test independently from the repository. |

The first compilation check exposed a linker path issue. The compiler's default `cc` alias depended on an unmounted host alternatives path. Selecting `/usr/bin/gcc` inside the existing read-only system mount fixed the problem. No home or credential mount was added.

## Interpretation limits

These checks validate the framework and its failure handling. They are not five successful server implementations. The new Level 2–5 contracts have not yet been exercised against complete accepted implementations, and no claim is made that every advanced positive protocol path has independent oracle validation. The first real builds may expose specification or evaluator defects; changing either requires a new frozen run and must be recorded as a new experiment version.

The host had 24 available CPUs and load averages of 13.85, 22.60 and 26.13 before the load-generator checks. Those runs validate accounting and concurrency, not a server speedup. No nginx baseline was installed or compared. The reports deliberately do not advertise a throughput winner.

No independent agent review was run. The available native delegation interface exposes no service-tier selector, so it was not used under the user's standard-speed requirement. Repository tests and direct CLI checks substitute for unavailable cursor-team-kit control tools.

## Prepared campaign

The local campaign is `.runs/http-campaign`. Its `prepared.json` lists all five generated run paths. It contains only the imported pilot charges, with $4.98708787 remaining and no pending request. The key file was checked for format without displaying its content. Preflight does not claim remote account or model-access validation.

The experiment's final result must distinguish API acceptance, performance coverage and security findings. Passing public checks is not a security certification. The current namespace/per-process sandbox is not an aggregate cgroup or VM boundary; see the walkthrough for that resource-isolation limitation.

## V3 sustained-improvement revision

The subsequent real Stage 1/2 runs are archived under results/2026-11-12-luna-rust-http. Their failures motivated v3. Stage 1 stopped on context capacity and later exhibited restart failures. Stage 2 stopped after two inconclusive comparisons with about ten minutes left.

The revised full test run passed 62 tests in 39.526 seconds. Additional tests cover refusing early finish despite acceptance and 99 recorded optimization attempts, refusing a plain final-message shortcut, accepting an honest partial report in the finalization window, context rollover before paid dispatch, preserved code/notes/spending, invalidation after restart failure, repair after invalidation, and campaign upgrades without forgiving charges. All five v3 launch packets pass local preflight and remain unstarted.

No live API run validates v3 improvement quality yet. The simulated API tests establish control-flow and accounting behavior, not that Luna will discover useful optimizations or security fixes. Security promotion remains subject to the existing evidence gates.
