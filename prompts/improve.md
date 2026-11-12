## Continue after acceptance

Your objective is the best validated implementation attainable within this run's remaining capacity. Passing the public suite is the beginning of improvement work. It is not permission to finish. One or two optimization attempts are not a stopping condition. Continue until the controller's finalization window or admission limit.

Preserve interface correctness first. Keep all public checks passing. Improve reliable service before chasing successful-request throughput. Then hill climb performance and investigate security risks. A candidate that loses correctness or fails to start cannot replace a working incumbent.

Repeat this loop while capacity remains:

1. Read budget_status and the latest results. Identify one concrete bottleneck, reliability failure or security hypothesis. State the mechanism and the expected observable result. Record it with record_iteration.
2. Make one bounded change. Submit complete source through submit_candidate. Do not stack untested changes. Work from the retained implementation unless explicitly investigating a failed challenger.
3. Test the hypothesis. Use the public checks, sandboxed run_tests, restart validation, and the full benchmark when it fits. Compare evidence, not intuition. Record observed results and the next hypothesis. The controller owns promotion; your journal does not declare a win.
4. Keep an improvement only when supported by the controller's gates. Otherwise keep the incumbent and change the hypothesis or category. Never weaken checks, hardcode fixture responses or conceal failures.
5. Continue. An inconclusive benchmark is not success and is not a reason to finish. Investigate the measurement limit or switch to security, stability, bounded resource use and test coverage. Do not repeatedly benchmark unchanged code or repeatedly ask to finish.

For performance, first address crashes, failed requests and timeouts under the declared 256/4096-client workloads. Then consider architecture, bounded queues, allocation/copy costs, syscall counts, backpressure, connection reuse and tail latency. Explain how a change should help before running it. Never call a generator-limited measurement a server speedup.

For security, review and exercise parser framing and integer boundaries, path normalization and symlink handling, allocation limits, slow clients, disconnect handling and descriptor/thread exhaustion. At applicable levels add pipeline desynchronization, host separation, upstream framing/retry behavior, cache isolation, TLS state handling and atomic reload. Use executable regression tests where possible. A review claim alone is not evidence of a fix. A passing finite suite is not proof that the server is secure.

Use run_tests for bounded tests of your Rust parsing, routing and resource-management logic. Use revalidate_candidate for three independent sandbox starts and complete public checks. Inspect server diagnostics. Treat a failed restart as a reliability defect even if a previous process passed every check. Revalidate the retained implementation during stabilization.

If the remaining time cannot fit a full paired benchmark, choose useful smaller work: a focused parser boundary test, malformed-input cases, overflow/property tests, a review of unsafe/FFI ownership with an executable test, or fresh-start validation. Preserve unpromoted security fixes and their evidence in candidate snapshots and the journal; do not claim an unpromoted change is the final artifact. Do not spend the final window starting a task that cannot finish.

Keep concise durable notes through record_iteration. Include hypothesis, change, observed evidence, verdict and next action. The controller may replace old conversation history with a checkpoint containing this contract, retained/latest source, reports and your recent notes. This preserves the same run and spending ledger; it does not grant a fresh budget or import another level's work.

Call finish only when budget_status reports can_finish=true. Use the final report to distinguish accepted behavior, measured performance, inconclusive results, demonstrated security fixes, unresolved risks and unpromoted experiments. If the controller interrupts work, the retained artifact and evidence must still be usable. Never claim maximal performance, complete security or completion merely because the minimum API works.
