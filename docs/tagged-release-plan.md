# Tagged release CLI

The user wants Terra to build an HTTP server, publish working Git releases during
implementation, and be graded on the last release if stopped at any time.

## Feature workflow

1. `how` over the affected subsystem. Complete. The controller owns immutable
   candidate snapshots and public reports. The runner exposes bounded tools. The
   sandbox owns generated compilation and execution. The new release module owns
   Git refs and grading snapshots.
2. `architect` for parallel design exploration. Two alternatives considered locally.
   Native delegates omitted because the launcher has no standard-tier selector.
   A free shell and agent-owned arbitrary tags would require a second protected
   evaluator and a broader execution API. Bounded init/release tools keep existing
   isolation and expose actual Git history without unrestricted host execution.
3. Write the throughput checkpoint as four todo items.
   - **Blocking first steps.** Freeze the active experiment before changing prompts.
   - **Independent workstreams.** Run monitoring stays in the original checkout.
     Release implementation and tests use a separate worktree.
   - **Shared mutable state.** One campaign owner writes each run. Git tags are
     append-only. Grading reads committed objects, never the working directory.
   - **Smallest safe decomposition.** One release module owns init, publish, list
     and grade operations. CLI and model tools call that module.
4. Delegate code-writing to a subagent using your configured feature model.
   Skip native delegation because the user forbids priority service and the native
   launcher cannot select service tier. Implement and review in separate passes.
5. Verify on the matching surface. Verified real sandbox Git, interrupted publication, dirty-tree grading and CLI exit codes.
6. Rebase into small, ordered commits. Stack follow-ups. Pending verification.
7. If the design is contested, `interrogate` before shipping. No contested design.
8. Run **Opening a PR**. Update the existing work PR after verification.

## Data and invariants

A release is a monotonically numbered `release/000001` Git tag pointing to a
commit containing main.rs and release.json. Metadata records the candidate ID,
source hash and public checks. Candidate IDs link to benchmark evidence in the run directory. A release must
compile, pass bootstrap, and retain every public check passed by the previous
release. A full-contract release cannot be replaced by a partial one.

The agent explicitly requests repository initialization and publication through
sandboxed tools. Initialization tags the recorded starter. Publications never
force-update tags. A crash before tag creation leaves the previous tag as the
last release. Grading reconstructs source from that tag in a fresh sandbox.
Correctness is graded before performance. Ineligible benchmark results remain
visible and never constitute a claimed performance improvement.
