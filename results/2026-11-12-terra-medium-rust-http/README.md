# Terra medium: independent HTTP server implementations

Both implementation runs completed on 2026-11-12 using `gpt-6.1-terra`, explicit
medium reasoning and `service_tier=default`. They started from empty candidate
directories and independent model histories. Stage 2 received no Stage 1 source.
Compilation and every server evaluation ran in fresh Bubblewrap sandboxes. Runs
were sequential to avoid benchmark interference, with 1,800-second limits each.
The existing shared $5 campaign ledger was retained; no budget reset occurred.

| Run | Public checks | Calls | Total tokens | API cost upper bound | Complete paired comparisons |
| --- | --- | --- | --- | --- | --- |
| Stage 1: static GET files | 11/11 | 60 | 2,216,292 | $0.50231330 | 4 |
| Stage 2: persistent HTTP, HEAD, pipelining | 16/16 | 43 | 1,646,673 | $0.42712665 | 2 |

These runs cost $0.92943995 combined. Including earlier Luna calls, campaign
spend is $1.00649019, leaving $3.99350981. All 103 Terra calls settled; no pending
reservations remain. Tokens include input, cached input and output; reasoning is
included in output, not added twice. Framework preparation outside the metered
runner is not included. Ledger-level Luna metadata describes the historical
campaign defaults; each new request's `profile` supplies its actual model/rates.

## Delivered artifacts and limitations

- [Stage 1 retained source](stage-1/retained.rs): passes the public suite and
  repeated fresh starts, but rejects valid headerless requests and suffers heavy
  failures at 4096 clients. [Parser repair](stage-1/candidates/02ec1b9e28124e6db987942b71a33ed1/main.rs)
  passed public checks and revalidation but was not promoted.
- [Stage 2 retained source](stage-2/retained.rs): epoll/sendfile server with
  persistent GET/HEAD and ordered pipelining. Passes the public suite and repeated
  fresh starts. Additional tests/source review identified header-byte compatibility,
  half-close handling, incomplete-pipeline timeout and pipeline-depth limitations.
  See the [model report](stage-2/model-report.md) and individual iteration records
  for the evidence and whether each issue was reproduced or only inferred.

Passing these finite suites does not mean full contract correctness. The controller
retained the first publicly accepted implementation in both stages. No challenger
passed its performance-promotion gate. Correctness repairs were archived but did
not replace the exported incumbent. This is a limitation of the current controller,
not evidence that the original code is the best implementation produced.

The next controller change should allow independently verified correctness repairs
to replace an incumbent without requiring a throughput gain. Add regressions to the
public suite, then use a sufficiently quiet benchmark environment before selecting
performance improvements. This run's gates and results were not changed afterward.

## Performance observations

All full paired comparisons were classified as generator/environment inconclusive.
Raw throughput and latency are diagnostic observations, not validated capacity or
speedup claims. Both 256 and 4096 active clients were exercised with 4 KiB and 64 KiB
responses; Stage 2 additionally measured persistent connections.

Two Stage 2 candidates illustrate useful implementation progress:

- Enlarging the listen backlog produced zero failures in both fresh 4096-client
  workloads in its paired measurement, versus 1,304 and 1,772 for the incumbent.
- TCP_NODELAY reduced observed small persistent-response p99 at 256 clients from
  44.5 ms to 5.1 ms, but other workloads regressed and the comparison was ineligible.

Neither change was promoted. Keep these observations separate from the retained
artifact's behavior. Candidate `benchmark.json` files contain complete round data,
including goodput, latency, failures, timeouts and generator eligibility.

## Reproduction and scope

Manifests, launch packets, specifications, candidate sources, compiler results,
public-check results, bounded implementation tests, iteration notes and benchmark
records are included. Binary hashes are in `summary.json`; binaries and raw API
responses are kept locally, not committed. Exact metered request settings and
charges are in `ledger.json`. Both runs completed three context rollovers while
preserving their own implementation and budget history.

The user clarified during Stage 1 that the objective is implementing the HTTP
servers, not a security-research campaign. Stage 2's launch packet records that
clarification. Historical model-generated category labels are preserved verbatim;
the activity reported here is server implementation, correctness testing and
performance measurement, with no separate exploit-development agent.
