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
