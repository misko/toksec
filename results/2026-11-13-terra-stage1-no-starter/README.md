# Stage 1 from scratch: Terra medium

Terra received no Rust starter or prior implementation. Standard service tier.
The earlier starter-based run was stopped at the user's request; its $0.20840830
charge remained in the same $3 campaign ledger. The replacement had fresh context
and retained the original campaign deadline.

The replacement produced one tag, `release/000001`, at 41.86 seconds. It passed
12/12 public API cases both during the build and in an independent post-run
rebuild. Three model calls used 69,197 tokens and $0.04802785. Total campaign cost
was $0.25643615. The run stopped after 42.01 seconds because the remaining
$2.74356385 could not cover the strict $2.745 next-call reserve. It did not complete
an optimization iteration and did not reach a performance ceiling.

All four independent performance measurements were ineligible. Both 4096-client
workloads recorded zero valid goodput; the 256-client workloads also had request
failures. Passing the API suite does not demonstrate successful high-load service.
There is one release point, not a measured hill-climbing trajectory.

The charts plot post-run measurements at release-publication time. Raw rounds,
failed-request counts and latency validity are preserved in timeline.json and
evaluation.json. No additional model calls were used for independent evaluation.
The subsequent partial-credit prompt change was not used in this completed run.

Restore the exported Git history with:

```sh
git clone implementation.bundle implementation
git -C implementation checkout --detach release/000001
```

Use framework commit e2d084e for the matching evaluator. The launch packet is
supplemented by the runner's tool definitions and Git instructions. Credentials,
raw model responses and compiled executables are not included in this archive.
