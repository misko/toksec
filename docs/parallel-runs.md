# Parallel Terra sandbox batches

`run_parallel.py` prepares independent campaigns, runs builders in separate
processes, then grades and publishes their final tagged submissions. It never
supplies starter code or comprehensive grading checks to builders.

```sh
python3 scripts/run_parallel.py prepare --directory .runs/terra-batch \
  --stages 1 5 10 --replicas 3 --parallel 3 --language cpp \
  --budget-usd 2 --wall-seconds 7200
python3 scripts/run_parallel.py run --directory .runs/terra-batch \
  --key-file ~/.codexapi
python3 scripts/run_parallel.py status --directory .runs/terra-batch
```

Preparation makes no model calls. The example authorizes nine independent $2
campaigns, with a maximum combined spend of $18. Each builder has its own ledger,
run ID, repository, namespace-isolated compilation/execution, and two-hour limit.
At most three builders run concurrently. Six disjoint logical CPUs are assigned
to each slot; queued runs reuse a slot only after its process exits. Other host
activity can still affect benchmark results.

Stage 1/5 campaigns explicitly select the `bounded-32k` request profile. It admits
only plain explicit text history and local tool schemas, using the provider token
count for the same request fields as generation. It rejects input above 32,000
tokens and caps generated output, including reasoning, at 16,000 tokens. It
reserves $0.200 at the pinned worst-case Terra rates before each request. Context
is compacted at 24,000 tokens; an oversized compacted request is rejected. It does
not send encrypted reasoning, server-side history references, or hosted tools.
Timeouts retain their reservation and block further admission. Stage 10 retains
its existing counted-request ledger and a $2 default allocation; explicit allocations up to $5 are supported. These guarantees
assume provider counting, pricing, and output-limit enforcement, as documented by
the existing counted-request backend. Historical runs keep their original policy.

The default single-run CLI retains its old reservation policy. Select the smaller
profile explicitly with `python3 -m toksec init --campaign PATH --budget-usd 2
--request-profile bounded-32k`, then prepare using Terra. Strict reservations may
stop a run before it spends the full balance. Neither budget nor parallelism
guarantees a working tagged implementation.

`batch.json` records all job paths, caps, CPU slots, statuses and timestamps.
Each raw run has `builder-process.log`, `parent-grading.log`, and `publication.log`.
The batch refuses automatic paid resumption after starting, including interrupted
runs. Inspect durable ledgers before considering a new campaign. The separate
`finalize` command retries grading/publication without model calls after builders
have stopped. Keep the recorded framework checkout unchanged during a batch.

Independent final grading and publication run sequentially after all builders
stop. API failure skips performance. Stage 10 remains partial/provisional and is
never represented as full acceptance. A run producing no tags is recorded as
`no_tag`; success means a tagged artifact was published, not that it passed every
API check. Consult each grade and its exit code. Results retain the usual
`results/<run-id>/` structure and latest index; all nine runs remain available.

## Budget sweeps

To create one implementation per stage at each of three caps:

```sh
python3 scripts/run_parallel.py prepare --directory .runs/terra-budget-sweep \
  --stages 1 5 10 --replicas 1 --parallel 1 --language cpp \
  --budgets-usd 3 4 5 --wall-seconds 7200
```

This prepares nine independent campaigns with a combined maximum of $36.
`--budget-usd` and `--budgets-usd` are mutually exclusive. All per-run caps must
be positive and at most $5. The sweep uses explicit Stage 10 allocations so the
requested $3/$4/$5 values are not silently reduced to its $2 default. Existing
ledger limits cannot change when reopened. Request-size bounds and reservation
policies remain unchanged.

For concurrent batches, launch preparation and execution with `taskset` on a CPU
set disjoint from all other batches. The scheduler only coordinates its own
slots; it does not discover or reserve other batches' CPUs.

## Coordinating already-running batches

`scripts/coordinate_batches.py` can adopt two or more live batch supervisors on
this 24-CPU host and enforce one global worker limit. It validates supervisor and
worker identities, pauses only the supervisors, saves a handoff record, then
replaces them without restarting the active workers. Linux pidfds track adopted
workers to completion. Only never-started jobs receive new CPU placements; their
original manifests are retained as `manifest.before-coordination.json` and their
execution placement is recorded explicitly. Paid run limits and ledgers do not
change. All final grading waits for the coordinated builders to stop.

```sh
python3 scripts/coordinate_batches.py --batch BATCH_A --batch BATCH_B \
  --state .runs/coordination.json --key-file ~/.codexapi \
  --results results --parallel 3
```

The handoff intentionally kills only stopped supervisor processes, bypassing
those supervisors' worker-cancellation handlers. It does not signal the active
builder sessions. It refuses existing coordinator state, unknown process IDs,
partially launched jobs, and attempts to restart already-started jobs. If it
fails before handoff, it resumes the original supervisors. A failure after handoff
requires inspection of the saved state and running workers, not a blind restart.

For the gateway campaign, prepare with `--stages 11 12 13 14 15 16 --replicas 3
--parallel 1 --budget-usd 3`. This allocates eighteen independent caps, runs one
worker at a time and cycles through all six stages before starting another replica.
A provider HTTP 429 pauses new admissions after active jobs drain. When capacity
is available, repeat the run command with `--resume-queue` and, for an archived
campaign, `--runner-root PATH_TO_FROZEN_CHECKOUT`. Only previously unstarted jobs
are eligible. Completed attempts and outstanding reservations retain their ledgers.

Gateway workers record a durable generation intent and a receipt for each tool
action. They use a 300-second generation read timeout within the original wall
deadline. The supervisor records the builder stop reason, settled spend, open
holds and grade outcome separately. A second consecutive ambiguous generation
timeout also pauses new admissions. A tested server returning HTTP 429 is an
ordinary test observation.

After a worker stops, inspect its latest tagged release, request phase, deadline
and outstanding liability. The following command performs local inspection.

```sh
python3 -m toksec recover --run RAW_RUN
```

Use `recover --run RAW_RUN --settle` to reconcile an already saved terminal
response offline. A request interrupted after dispatch without a response keeps
its full hold. An action interrupted between dispatch and its durable tool
receipt requires inspection of the last completed tag. When the inspection
reports `continuation_possible`, the following explicit continuation keeps the
same run identity, original deadline, sandbox assignment and ledger. Use the
original CPU affinity and preparation checkout.

```sh
taskset -c ORIGINAL_CPU_LIST python3 -m toksec run --run RAW_RUN --resume --key-file ~/.codexapi
```

After an interrupted batch drains the queue, `paused_recovery` leaves the raw
run open for inspection. To close and publish the retained releases, use
`python3 scripts/run_parallel.py finalize --directory BATCH --results results`.
Finalization seals the builder. A working tag can still be graded when its last
generation timed out. Financial holds survive finalization.
