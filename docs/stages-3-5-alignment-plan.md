> Implementation: [v8 protocol and validation](stages-3-5-v8.md).
> The proposal below is retained as design history; performance launch readiness
> remains limited by the measured generator bottleneck.

# Align Stages 3–5 with the current experiment protocol

Status: proposed plan, 2026-11-14. Review baseline: `http-v7`, commit
`fb40e7c`. No evaluator changes or new model runs are authorized by this document.
Existing runs retain their frozen contracts and graders.

## Findings

Stages 3–5 have feature contracts and some grading coverage, but do not yet use
the Stage 1–2 experiment protocol consistently.

| Area | Stages 1–2 today | Stages 3–5 today | Required alignment |
|---|---|---|---|
| Starting code | Starter rejected | Legacy starter accepted | Reject starters for every stage |
| Development API feedback | Minimal smoke only | Full grading feedback | Smoke only on every builder path |
| Test disclosure | English contract plus smoke descriptions | Full case descriptions included in packet | Keep full English requirements; withhold grading cases |
| Development fixtures | Ordinary files | Full fixtures used by benchmarks | Separate minimal development fixtures for all stages |
| C++ | Supported | Rejected by language profile | Enable approved C++ profile after contract alignment |
| Stage definitions | Dedicated stage modules | Inline specification and extended checks | Shared catalog with explicit stage selection |
| Shared prose | Mostly matches behavior | Contradicts inherited requirements | Compose an unambiguous resolved contract |

Specific implementation evidence:

- `toksec/controller.py`: starter restriction and `visible_smoke_only` scope
  apply only to stages 1–2. Submission/revalidation select smoke by `level <= 2`.
- `toksec/specification.py`: higher-stage packets expose full case descriptions
  despite text claiming grading is held out. Higher stages include Stage 2 prose
  plus inline additions rather than dedicated resolved contracts.
- `toksec/sandbox.py`: development benchmarks select minimal fixtures only for
  stages 1–2. Feedback filtering alone would not fix fixture exposure.
- `toksec/languages.py`: C++ accepts only stages 1–2.
- `stages/common/HTTP.md`: missing Host is allowed, directories are forbidden,
  and request bodies/Transfer-Encoding are rejected. These conflict with Stage 3
  host/index rules and Stage 4 proxy body rules unless explicitly scoped.

The current host catalog has 12/21/25/29/35 check groups across stages 1–5,
respectively. These are groups, not counts of individual inputs or a measure of
coverage completeness. Current performance matrices contain 4/8/8/12/20 workloads.

## One experiment protocol

All five stages should be independent, from-scratch assignments. Higher stages
include more required capabilities, but receive no earlier implementation,
conversation, starter, or host grading feedback.

Keep these rules in `RULES.md`:

- Agent chooses architecture, debugging, tests and optimization strategy.
- English contract, executable interface, resources and scored workload definitions
  are disclosed. Only a few normal API examples are supplied as executable checks.
- Agent designs its own tests; supplied smoke success is provisional evidence.
- Compilation, candidate execution and agent-authored tests remain sandboxed.
- Agent creates a private Git repository and explicitly publishes working tags.
  Last completed tag is the submission; untagged changes do not replace it.
- Award progress credit for independently validated improvement between tags,
  not tag count. Freeze a scoring rubric before using numerical total grades;
  until then report API counts, correctness regressions and eligible performance
  changes separately rather than inventing a weighted score.
- Final host grading compiles each tagged source independently. Any required API
  failure skips that tag's performance grading and gives zero performance credit.
- Use remaining admitted capacity for useful improvements; publish early because
  the next model call is not guaranteed. Preserve the strict spending reservation.

Language restrictions belong in language profiles. HTTP semantics belong in
capability contracts. Budgets and deadlines belong in the frozen run manifest:
render their actual values into the packet rather than hard-coding a shared dollar
amount into generic rules. Proposed future runs retain Terra medium, default
service tier, $3 per stage and a two-hour builder ceiling unless changed explicitly.
This plan does not launch them. Host grading time and compute are reported separately.

The file/process interface remains the same: a complete `main.cpp` or `main.rs`,
the existing configuration/launch interface, and controller-managed compilation,
tests and releases. Document that agent-authored test programs must arrange their
own test setup; do not imply a server is already listening. Consider a bounded
helper that runs an agent-authored client and candidate in the same private network
namespace, with agent-authored fixtures. This provides execution capability, not
a comprehensive test implementation.

## Stage scope and minimal supplied checks

Use shared Stage 2 smoke behavior for higher stages: ordinary GET, ordinary HEAD,
and two sequential GETs on one persistent connection. Use a valid configured Host
on all of them. Add just one normal feature check for each higher stage; do not
accumulate every earlier stage's extra example.

| Stage | Required capabilities | Proposed extra visible check |
|---|---|---|
| 3: hosts and routing | Stage 2 behavior, virtual hosts, aliases, redirects, directory index, MIME, ETag, one byte range | GET an ordinary file from the second configured host |
| 4: reverse proxy | Stage 3 capabilities plus GET/HEAD/POST proxying, framing, upstream selection/reuse, deadlines and bounded bodies | GET through one healthy upstream and verify returned bytes |
| 5: operations, proposed bare-bones profile | Stage 4 capabilities plus bounded response cache, rate limiting, atomic reload and graceful drain | Repeat an ordinary cacheable GET and observe a normal cache hit |

Do not supply malformed-input, missing-field, oversized-input, timing-boundary,
pipeline or failure-recovery examples. The English requirements still state all
required behavior. Minimal upstream fixtures must not contain the held-out fault
injection endpoints. Stage 5's simple cache-hit example can use an ordinary
upstream request counter; richer cache tests remain host-only.

### Stage 5 decision needed before implementation

Existing Stage 5 requires maintained-library TLS and library gzip. The latest C++
policy prohibits those dependencies, and the existing contract explicitly forbids
implementing cryptography from scratch. They cannot be combined unchanged.

Recommendation: define a new, explicitly named **bare-bones operations profile**
without TLS or gzip for the default Rust/C++ comparison. Preserve the old TLS/gzip
contract under its existing version. If desired later, add a separate profile
explicitly approving OpenSSL/zlib in both languages, with its own benchmarks.
This is a proposed scope change requiring agreement, not an implemented decision.
Never compare different profiles as if they satisfy the same Stage 5 contract.

## Canonical contracts and test catalog

Proposed structure, preserving thin stage-specific API/performance selectors:

```text
RULES.md
stages/
  common/INTERFACE.md
  common/BENCHMARK.md
  languages/{rust,cpp}.md
  capabilities/
    parsing.md
    static-files.md
    persistence.md
    routing.md
    proxy.md
    operations.md
  stage1/ ... stage5/
    SPEC.md               # stage-specific scope and configuration
    profile.json          # selected capabilities, suites and language profiles
    api.py                # catalog selection, not duplicate test bodies
    performance.py        # declared workload selection
evaluation/
  api/                    # host-side superset, grouped by capability
  performance/            # shared workload engines and metrics
  smoke/                  # minimal supplied checks and ordinary fixtures
  fixtures/               # host-only edge/fault data
evaluate.py
```

Keep one canonical catalog, with stable case IDs, contract references, applicability
and visibility metadata. Stages select from it; languages use identical protocol
checks. Importing shared helpers must not expose the host catalog to builder tools.
The final layout is an implementation choice, but this separation is mandatory.

Resolve requirements by capability rather than “later text wins”: Stage 1–2 Host
policy differs from Stage 3–5; directory routing is enabled only where required;
local routes reject request bodies while proxy routes support the declared methods
and framing. Generate one unambiguous packet and validate it before a run.
Include all new catalog files and manifests in the evaluator fingerprint.

## Held-out API coverage to strengthen

This is a host implementation checklist, not a new builder handout. Every scored
expectation must trace to a disclosed requirement; clarify ambiguous behavior in
the contract before freezing tests.

| Catalog area | Coverage emphasis |
|---|---|
| Shared parsing/files | Fragmentation, framing, exact bytes, confinement, limits, deadlines, disconnect recovery |
| Persistence | HEAD, ordered pipelines, connection/request limits, partial writes and slow-client isolation |
| Routing | Host normalization, alias confinement, query-preserving redirects, index selection, conditionals before ranges, ranges on each representation |
| Proxy | Fragmented chunks, trailers, conflicting lengths, malformed/truncated upstream responses, hop headers, reuse, retry boundaries, POST not retried, timeout/recovery |
| Operations | Cache separation/bypass/expiry/eviction, HEAD interaction, limiter behavior, valid/invalid atomic reload, genuinely in-flight draining |
| Optional TLS/gzip | Explicit TLS-version behavior, HTTPS routing, compressed representation headers, negotiation and interactions |

Avoid overstating black-box evidence: cache probe behavior is not proof of internal
memory accounting. Use deterministic fixtures and synchronization for reload/drain
tests, not a sleep that assumes a response is still in flight. Validate the suite
with known-good fixtures and intentionally faulty implementations.

## Performance that measures the added capabilities

Keep comparable static baselines: 256/4096 clients, 4/64 KiB bodies, fresh and
persistent connections, five rounds and the existing timing/resource limits.
Report successful goodput, latency distributions, failures/timeouts, CPU and RSS.

- Stage 3: retain static baseline; disclose a routed-file workload exercising
  multiple configured hosts/aliases. Keep range/conditional behavior primarily
  in API grading unless separately declared as scored workloads.
- Stage 4: add persistent proxy traffic with controlled healthy upstreams. Allocate
  upstream fixtures separate CPU resources from the server and load generator,
  record their utilization, and flag upstream saturation as invalid attribution.
- Stage 5: explicitly measure cache bypass/miss and warm cache-hit workloads with
  deterministic setup. Declare cache size, dataset and TTL so measurement does not
  silently switch between hits and misses. Rate limiting remains disabled for
  throughput measurement; reload/drain remain API checks unless separately scored.
- Optional TLS/gzip profile: declare distinct TLS handshake/reuse and compression
  workloads rather than combining their results with plaintext operations.

Calibrate the harness before more paid experiments. Earlier measurements often
reported load-generator saturation; raw RPS then cannot establish server speedups.
Use a known fast reference to show the generator and upstream fixtures have headroom
at both client counts. Preserve eligibility thresholds instead of relaxing them
to manufacture valid results. Version any measurement-engine changes.

Allow development evaluation of a selected declared workload for affordable hill
climbing; keep full declared matrices for final grading. Print the exact scope on
every report. Invalid or unmeasured results receive no claimed performance gain.
Plot every tag's API progress and eligible workload metrics against publication
time, displaying failed/ineligible measurements explicitly.

## Implementation sequence and completion criteria

1. **Freeze semantics and profiles.** Agree Stage 5 scope; resolve inherited
   contradictions; create dedicated Stage 3–5 scope/configuration documents.
   Done when each supported stage/language produces one consistent packet and
   every scored behavior has a contract reference.
2. **Make stage policy uniform.** Reject starters for all stages; enable supported
   C++ stages; apply smoke-only behavior to submissions, revalidation, benchmarks,
   releases, retained evidence, rollover and final agent reports. Rename misleading
   development `full_acceptance` fields with a versioned migration.
   Done when automated isolation checks demonstrate no held-out names, counts,
   fixture contents or results reach any builder path.
3. **Organize and strengthen the catalog.** Move existing checks without losing
   coverage, add minimal higher-stage smokes and missing contract-backed cases.
   Done when known-good and intentionally faulty fixtures verify grading and when
   API failure reliably suppresses final performance for both languages.
4. **Calibrate performance.** Separate upstream resources, declare feature-specific
   workloads and permit scoped development measurements. Done when reference runs
   demonstrate valid measurements at 256/4096 clients or clearly identify an
   unresolved harness bottleneck. Do not launch for performance conclusions while
   that bottleneck persists.
5. **Dry-run the complete lifecycle.** Exercise from-scratch compilation, private
   Git initialization, multiple tags, interruption and grading from the last tag.
   Make worker status durable, distinguish builder completion from grading, and
   resume interrupted grading without new billable model calls. Done when exports,
   plots, spend ledger and final source remain recoverable after interruption.
6. **Run progressively after launch authorization.** Stage 3 first, inspect protocol
   and harness behavior, then Stage 4 and the agreed Stage 5 profile. Keep separate
   per-run ledgers, frozen versions and independent contexts. Do not interpret
   strict reservation early stopping as exhaustion of possible optimizations.

Implement in a new worktree/version so active and historical experiments remain
reproducible. Documentation review alone does not change their fingerprint.
