# Declared benchmark design

Status: uncalibrated design, not an executable benchmark contract yet. Final
numeric durations, class rates and validity thresholds must be frozen in the
published workload manifest before an agent run. The agent receives that manifest;
only workload implementation and sampled fault schedules remain host-only.

Final performance requires the complete API gate. Development benchmarks are
provisional and may run against a smoke-accepted candidate. Do not interpret a
successful visible HTTPS GET as full correctness or performance acceptance.

| Family | Transport | Body | Concurrency | What is measured |
|---|---|---|---|---|
| Static fresh | HTTP, TLS 1.2, TLS 1.3 | 4/64 KiB | 256/4096 | Full connection/request latency and useful responses/s |
| Static persistent | HTTP, TLS 1.2, TLS 1.3 | 4/64 KiB | 256/4096 | Steady response latency and goodput |
| Proxy persistent | HTTP, TLS 1.2, TLS 1.3 downstream; HTTP upstream | 4/64 KiB | 256/4096 | Correct proxied goodput, queue pressure, upstream attempts |
| Cache hit/miss/refresh | HTTP and HTTPS | 4/64 KiB | 256/4096 | Response latency and origin request reduction |
| Streaming | HTTP and HTTPS | 16 MiB transfers with small-request side traffic | Calibrated bounded transfer concurrency | Time to first byte, bytes/s, memory and small-request tail latency |
| Mixed recovery | HTTP and HTTPS | Declared mix | 256/4096 total | Per-class goodput, tail latency and recovery after disruption |

Run server process-tree profiles of 1, 2 and 4 CPUs, always with the same 512 MiB
aggregate memory budget. Use five repetitions for scored workloads. Fix and record
TLS protocol/cipher/key parameters. TLS session resumption and early data are off.
Report fresh full-handshake and persistent measurements separately. Clients verify
certificate chains/hostnames and exact decrypted payloads. No resumption or TLS
verification bypass is permitted merely to improve the measured number.

Report successful requests/s, useful bytes/s, p50/p95/p99, errors by status/type,
connect/handshake/response timeout phases, rejection rate, CPU and charged memory
for the entire candidate process tree. Retain upstream request counts, worker
replacement events, per-class results, per-round spread and eligibility reasons.
Account for exited/replaced workers as well as live processes.

Generator and fixture CPUs are outside the server allocation. Calibrate TLS
handshake capacity and upstream capacity separately. Track scheduling wait or
equivalent stall evidence for server and upstream, not only generator lag.
Insufficient load-generation capacity makes a round inconclusive. Do not promote
an ineligible measurement or hide failed/rejected requests in successful latency.

The published mixed-workload schedule must specify class proportions, request
sizes, offered-rate or closed-loop semantics, warmup/measurement/drain periods,
fault windows, allowed interrupted requests and recovery deadlines. No hidden
requirements may be introduced through the schedule. Until that manifest and
calibration exist, no Stage 10 performance grade can be issued.
