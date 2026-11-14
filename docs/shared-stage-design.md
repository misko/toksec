# Shared rules and independent stages

The user wants independent from-scratch Stage 1 and Stage 2 builds, one shared
instruction source, separate stage API/performance suites, and independent grading.

## Feature workflow and throughput checkpoint

1. `how` over the affected subsystem. The runner currently assembles a prose
   packet plus all evaluator source. The specification concatenates inherited API
   strings, including rules later overridden. Checks and workload definitions are
   centralized. The controller owns immutable submissions and Git releases.
2. `architect` for parallel design exploration. Two designs considered locally:
   independent complete stage folders duplicate policy and protocol rules; shared
   policy/contracts plus stage-owned registries avoid that duplication. Choose the
   latter. Native delegation cannot select the user's required standard tier.
3. Write the throughput checkpoint as four todo items.
   - Blocking first steps. Preserve the running experiment in its checkout. Work
     on a new branch/worktree and freeze the new contract as v5.
   - Independent workstreams. Prompt layout and evaluator structure are separate
     concerns, but share the packet registry and need one migration owner.
   - Shared mutable state. Each prepared run snapshots its input documents. Never
     rewrite historical packets or attach new tests to the active experiment.
   - Smallest safe decomposition. Shared documents, stage registries, then
     independent regression checks and CLI verification.
4. Delegate code-writing to a subagent using your configured feature model.
   Unavailable with the user's required service-tier control. Implement locally
   and review the assembled packets and behavior in a separate verification pass.
5. Verify on the matching surface. Run package tests and the actual evaluator CLI.
   Use repository checks in place of unavailable control-cli/deslop tooling.
6. Rebase into small, ordered commits. Commit the integrated migration after tests.
7. If the design is contested, `interrogate` before shipping. No contested design.
8. Run Opening a PR. Keep the existing work branch available for review.

## Data model

A stage combines shared RULES.md, the shared executable interface and HTTP file
semantics, one stage-specific SPEC.md, a registry of API cases and a workload list.
The same selected registry drives the packet's case list and the host evaluator.
Stage 2 never imports Stage 1's contract or implementation. It shares only common
HTTP checks and measurement utilities.

Builder inputs contain English requirements and workload parameters. Independent
checker implementations are host-owned and are not injected into builder context.
The agent may use the provided tools or its own Rust tests in any order. No
mandatory journaling, optimization count or prescribed architecture is required.
The budget remains a strict $3 campaign ceiling. No paid run is launched by this
refactor. Numeric milestone weights remain undefined. API failure forfeits all
performance credit and skips performance execution.
