# Shared measurement contract

Each declared workload uses 256 or 4096 active clients and 4 KiB or 64 KiB
responses. Four trusted client workers run five rounds per workload. Each round
has one second of warmup, three seconds of measurement and a two-second request
deadline. There is one outstanding request per client. Persistent workloads do
not benchmark pipelining. Fresh latency includes connection setup; persistent
latency includes reconnecting when required.

Count valid responses only after checking status and exact payload bytes.
Report requests per second, payload bytes per second, p50/p95/p99 successful
request latency, failures, timeouts, round spread, server CPU and peak RSS,
client CPU and event-loop lag. Failures are not silently retried out of the
statistics. These closed-loop workloads do not promise an open-loop arrival rate.
Excess generator lag or saturation makes a measurement inconclusive.

The supplied comparison tool alternates incumbent/challenger rounds. Its
conservative diagnostic promotion requires eligible error-free measurements,
no more than a 5% p99 regression, separated throughput ranges and at least a 5%
geometric-mean throughput gain. You may choose other diagnostic experiments.
The host's final grade uses your tagged source and the declared full matrix.


Stage 3 adds persistent routed files from beta.test via the alias prefix, using
the same payload sizes. Stage 4 adds persistent proxy GETs to healthy upstreams.
Proxy/operations runs require a sixth CPU dedicated to the trusted upstreams,
separate from the server and four generators. Upstream utilization above 90%
makes the measurement ineligible. These resources are reported in each round.

Stage 5 adds cache-hit and cache-miss workloads. Benchmark configuration sets
cache_ttl_ms=60000, cache_bytes=4194304 and rate_per_second=0. A cache-hit round
repeats one URL whose upstream sends public,max-age=60; the one-second warmup
primes it before measurement. A cache-miss round repeats a URL with max-age=0,
so responses must not be reused. Both return the ordinary 4/64-KiB payloads.
No TLS or gzip is measured in the bare-bones operations profile.

benchmark_candidate accepts a declared workload ID for a smaller diagnostic run,
or null for the full matrix. Subset measurements do not promote a full-matrix
baseline. Every result identifies its selected workloads. Final grading still
requires full API acceptance followed by the complete declared matrix.

For Stages 11–16 the parent also checks the declared downstream effects. Origin
and authorization counters include warmup. Protected responses require a fresh
decision each time. Caching workloads must demonstrate reuse. Refusals and
timeouts cannot earn successful delivery throughput. The mixed state and quota
checks run in the API gate. Stage 14 measures local service and admitted gateway service separately, with
both burst limits set to ten million during performance rounds. Cache performance uses a 60-second TTL and uploads use 256 MiB aggregate
and tenant quotas and a two-second upload deadline during load measurement.
