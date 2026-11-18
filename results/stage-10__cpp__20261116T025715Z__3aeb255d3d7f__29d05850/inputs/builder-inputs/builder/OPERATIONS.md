# Cache, worker and recovery behavior

This file defines Stage 10 additions to HTTP.md. Configuration directive names
and values are in CONFIGURATION.md. All deadlines use monotonic time.

## Cache and coalescing

Cache successful proxy GET responses with explicit Cache-Control:
public,max-age=N, capped by the configured cache TTL. The key includes downstream
scheme, normalized HTTP host, target path and query. Honor Vary: Accept-Encoding
using its exact request field value, with absence distinct from a present value.
Bypass Vary:*, other Vary names, Authorization requests and Set-Cookie, private or
no-store responses. Do not cache partial responses, malformed/truncated bodies,
or 5xx errors. HEAD may read a completed GET entry but never populate one.

An expired entry with an ETag uses If-None-Match upstream. If it lacks ETag but
has Last-Modified, use If-Modified-Since. A valid 304 refreshes the stored body
using returned freshness/validator headers, retaining absent stored fields;
return a normal body-bearing 200 to an unconditional GET. A fresh 200 replaces
the entry only after its complete body validates. Without a validator fetch a
new representation. Never serve an expired entry on refresh failure in this
profile. Complete waiters with the applicable 502/504 and permit later recovery.

Store cache entries and coalesce misses within each worker. A single-worker cold
burst for one cacheable key produces one in-flight upstream fetch. With W workers
at most W simultaneous fetches are allowed for that key. Partition the configured
total cache body-byte allowance equally across workers; unused shares need not
be borrowed. Metadata and waiting requests must also be bounded by explicit entry
and waiter limits. The memory budget applies to the entire process tree.

Do not coalesce POST, HEAD misses, Authorization requests or different variants.
Before Vary is known, include Accept-Encoding in the pending key. When a response
proves noncacheable or too large for a worker's cache allowance, release waiters
into ordinary FIFO proxy admission; do not silently reuse that response for them.
Queue deadlines continue from each waiter's original arrival. The initiating
client's disconnect must not cancel a fetch with remaining live waiters. With no
clients left, abort the upstream exchange and do not retain a partial entry.

## Global limits and upstream failure policy

Rate limiting and configured connection/admission limits apply across all workers,
not independently per worker. The global HTTP request limiter is a monotonic token
bucket with the configured rate/burst. Rejections are 429 with Retry-After: 1.
Benchmarks disable the request limiter except designated correctness/fairness cases.
Separate configured upstream groups have separate FIFO admission queues and limits.
Retries share their request's admission budget; they do not create unlimited work.

After an endpoint's configured consecutive transport/deadline failure threshold,
exclude it from new selection for the configured cooldown. Existing exchanges may
finish. After cooldown permit a single probe exchange at a time; success restores
eligibility, failure restarts cooldown. With no eligible endpoint or available
probe, return 503 with Retry-After: 1. Valid upstream HTTP error responses do not
by themselves count as transport failure. Keep protocol-invalid connections out
of the reusable pool. The directive table specifies the threshold/cooldown values.

## Master and workers

Run exactly the configured 1, 2 or 4 workers beneath one foreground master. Use
the same executable; no external helpers. Each worker must be able to serve all
configured listener types. Threads and the I/O mechanism remain implementation
choices. Global limits may use any permitted IPC strategy.

If the host kills one worker, the master replaces it within two seconds after
observing exit. Requests owned by that worker may fail. Other workers must remain
serviceable, and the process tree must not accumulate zombies or leaked IPC.
Tests identify workers through the process tree, not a candidate-supplied PID list.
Cache contents owned by an exited worker may be lost. Global admission/rate-limit
state must recover that worker's reservations without permanently reducing capacity.

SIGHUP validates an entire new configuration plus TLS material before publication.
CONFIGURATION.md enumerates immutable directives and fixed run-manifest resource
budgets; changes to those directives reject the reload. Other documented reloadable settings switch
as one generation. New connections use the new generation within two seconds.
Existing connections and in-flight operations may finish on their accepted
generation. Their keepalive lifetime ends at the configured drain deadline.
This is an explicit Stage 10 change from Stage 5's subsequent-request reload scope.

Flush cache for the new generation; old in-flight responses cannot repopulate it.
Reset the single global limiter on a successful generation change; old and new
connections both consume the newly configured bucket. Preserve upstream group
reservations across generations, keyed by the immutable group name. Cache/admission state retained
by old connections still counts against process-tree resource limits. An invalid
reload leaves the active generation, certificate and listeners serving unchanged.
The old and new configurations are immutable snapshots from request processing's
perspective; internal representation remains the agent's choice.

SIGTERM stops new accepts within 250 ms, finishes in-flight responses up to the
configured drain deadline, and exits the complete process tree within that deadline
plus 500 ms. Idle connections close; an incomplete request cannot extend draining.
Never start replacement workers while shutting down.

## Sustained operation

Independent correctness tests combine disconnects, queue pressure, cache expiry,
failed reload, certificate rotation and worker exits. Required behavior is the
same as above even when events overlap. A worker kill may interrupt its owned
requests; it does not waive correctness for responses that are completed.

After clients close and configured idle/pool deadlines pass, live socket and queue
reservations must return to their pre-wave baseline, apart from explicitly bounded
idle pools/cache entries. Repeat waves must not grow descriptors, processes or
charged memory without bound. Host tests disclose allowed accounting tolerance
and observation deadlines before this packet is frozen for launch.
