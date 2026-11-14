# Shared builder rules

Build a working, efficient HTTP server that satisfies the selected stage's English
contract. Stages 1 and 2 are independent from-scratch assignments. No Rust starter,
previous implementation, or another run's conversation is supplied.

## Freedom to work

You choose the architecture, order of work, debugging strategy, tests and
optimizations. You may use the evaluator tools, supply your own Rust tests, or
reason about a change before testing it. There is no mandatory iteration sequence,
number of experiments, journal entry, or implementation technique. Tool access,
the source/process interface, sandbox limits and the grading contract still apply.
Testing correctness first, addressing failed requests before speed, and measuring
one change at a time are suggestions. The goal is a working and very efficient
implementation, not compliance with a prescribed development process.

## Testing is part of your task

You are responsible for designing and running tests for your implementation.
Infer what needs testing from the English contract; do not rely on the supplied
checks as a comprehensive test plan. Choose your own cases, tools and strategy.
Providing only enough behavior to pass supplied examples does not satisfy the task.

The English requirements are authoritative. Supplied smoke checks demonstrate
basic API usage only; passing them is not evidence of full correctness. The host
may independently evaluate any behavior required by the contract. It must not
introduce undocumented requirements. No starter implementation is supplied.

Develop and retain your own correctness evidence before publishing releases.
You choose how much capacity to spend on tests versus implementation and
optimization. Report what you tested and any known limitations honestly. Passing
a finite suite does not prove complete correctness or maximum performance.

## Deliverable and Git releases

Submit a complete main.rs through submit_candidate. Compilation and execution
occur in sandboxes. Controller tools are your filesystem/execution interface;
you do not have a general host shell. Additional Rust tests run through run_tests.

You can be stopped at any time. After your first working submission, call
init_repository to create a new private Git repository and its first release tag.
Use release_candidate to publish periodic working milestones. Each numbered tag
contains main.rs and controller-generated release.json evidence. The last completed
tag is your final submission. Untagged edits do not replace it. No tag means no
submission, and stopping before the first working tag can leave no deliverable.
Published releases must compile, pass bootstrap and preserve previously passing
visible smoke checks. Publication is explicit; submitting source alone does not publish it.

You receive partial credit for validated progress since the previous tag, even
if you do not finish the target. Explain the before/after evidence in each release
note. New passing API checks, demonstrated reliability repairs and valid measured
performance improvements are progress. Duplicate source, cosmetic edits, repeated
claims and extra tags alone earn no additional credit. Do not deliberately split
an easy solution to inflate the milestone count. Numeric milestone weights are
not yet defined.

## Development feedback

submit_candidate and revalidate_candidate run only the supplied smoke suite.
The full host API suite is held out until the run ends. Tool fields named
full_acceptance refer only to the supplied smoke suite, not final correctness.
benchmark_candidate provides provisional ordinary-traffic performance feedback
after smoke acceptance. Such measurements do not establish final eligibility.
Release metadata and retained baselines contain development evidence only.

## Grading

The host grader extracts the last tagged source and compiles it independently.
API correctness is graded first. If compilation or any required API check fails,
performance is not tested and is graded as failed, with zero performance credit.
Failed API checks reduce API credit; the performance credit is also forfeited.
A fast incorrect implementation cannot recover those marks through throughput.

If all API checks pass, the host measures the declared workloads. It reports valid
goodput, latency, failures, timeouts, CPU and memory. Missing or ineligible
measurements earn no demonstrated performance credit. Successful-request latency
must be read alongside failures. A saturated load generator is not evidence of a
server speedup. Reliability, then throughput and latency, are suggested priorities.
The controller's retained comparison baseline is diagnostic; your explicit last
tag determines the final implementation.

## Capacity

The configured campaign cap is $3. The controller reports the actual remaining
shared dollars, tokens and wall time through budget_status and before each model
call. All model input, output, reasoning and final reporting consume that budget.
Compilation and evaluation CPU are tracked separately. The strict worst-case
reservation policy can stop admission well before $3 of settled spend.

Use the available capacity to improve your result. You choose which experiments are worth doing. Continue improving until the
finalization window or admission capacity is exhausted; then use finish. The controller enforces the spending and wall
ceilings regardless of that decision. Do not assume another call will be available
for publication. Record limitations and unmeasured claims honestly in your report.
