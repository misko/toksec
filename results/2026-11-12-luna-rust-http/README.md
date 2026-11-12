# Independent Rust Stage 1 and Stage 2 runs

Both runs used fresh Luna contexts and empty candidate directories, standard processing, sandboxed Rust compilation/runtime, and the same $5 campaign ledger. The framework was frozen at commit aeb1929. No generated source was edited by the supervising agent.

| Stage | Acceptance during build | API calls | Total tokens | API cost upper bound | Builder wall time | Stop reason |
|---|---|---:|---:|---:|---:|---|
| 1 | 11/11 public checks | 15 | 696,214 | $0.03973747 | 331.39 s | 64,000-token request context ceiling |
| 2 | 16/16 public checks | 10 | 353,414 | $0.02440064 | 1,211.58 s | Model finished after two optimization comparisons |

Combined new API cost was $0.06413811. Including the earlier Python pilot, campaign cost was $0.07705024, leaving $4.92294976. Costs exclude unmetered framework preparation and local benchmark compute. Tokens include repeated/cached inputs and outputs. Reasoning is already included in output usage. See summary.json and ledger.json for the exact records.

## Reliability and performance qualification

Stage 1 passed once during its build but was not reliably restartable afterward. A separate sandbox reproduction exited 101 with a Rust thread-spawn panic and OS EAGAIN, “Resource temporarily unavailable.” Do not describe this artifact as reliably working merely because the initial acceptance report passed.

An initial post-run benchmark attempt aborted on startup failure. A subsequent explicit 20-round matrix recorded every round outcome. Twelve rounds completed and eight failed to start or complete the trusted driver. Completed rounds also had request failures. No full five-round workload was available, so the incomplete summaries cannot establish performance. These operator measurements made no API calls and are separate from builder wall time. They are preserved in stage-1/postrun-benchmark.json.

Stage 2 completed a 40-round baseline and two 80-round paired comparisons. Both comparisons were rejected as generator/environment inconclusive. The original accepted candidate was retained. The model's final report identifies its thread-per-connection design and substantial failures at 4096 clients. No improved-throughput or reliable-4096-client claim is supported. Full benchmark reports are in stage-2/candidates/.

These are functional acceptance observations and negative performance/reliability evidence, not security certifications. The runner did not conduct a separate attacker campaign.

## Artifacts and reproduction

Each stage contains the unedited retained main.rs, build metadata, acceptance report, frozen launch packet/specification, run state/result, and reports from other candidates. Binary hashes are in summary.json. Binaries and full response/tool records remain in the local .runs/http-campaign/runs directories. Source is archived for reproducibility; raw model reasoning is not published.

The original result.json records the controller's decision at run completion. Read it together with the post-run qualification above. Do not rewrite historical acceptance to conceal the restart failure.

## Lessons for the next framework revision

- Acceptance must start sustained optimization and hardening, rather than permit finishing after one comparison.
- Request context grows because full source submissions and feedback remain in history. Preserve durable checkpoints and compact the active conversation before hitting its limit.
- When the remaining time cannot fit a full benchmark, spend it on bounded security tests, restart stability, and targeted validation rather than immediately finishing.
- Repeated startup checks and captured server stderr are necessary. A single passing process was insufficient to establish restart reliability.
- Inconclusive measurements should trigger a different useful investigation, not repeated claims of improvement or blind benchmark repetition.
