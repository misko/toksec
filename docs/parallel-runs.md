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
its existing counted-request ledger and $2 maximum allocation. These guarantees
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
