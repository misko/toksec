# Stage 10 preparation packet

This is a concrete instruction and fixture draft for review, not a runnable
Stage 10 evaluator. No model campaign or candidate server was launched. See
[host readiness](host/READINESS.md) for the launch gates still missing.

## What the agent receives

The instruction order is [START](builder/START.md), [RULES](builder/RULES.md),
[INTERFACE](builder/INTERFACE.md), the selected language policy,
[HTTP](builder/HTTP.md), [CONFIGURATION](builder/CONFIGURATION.md),
[TLS](builder/TLS.md), [OPERATIONS](builder/OPERATIONS.md),
[BENCHMARK](builder/BENCHMARK.md), and [SMOKE](builder/SMOKE.md).
An assembled preview for each language lives in `preview/`. The launch system
must provide the selected preview's content in model context and make allowlisted
fixture bytes accessible through its sandbox tools; host paths alone are not a
usable agent filesystem interface.

The agent also receives a minimal bootstrap configuration, a full example with
includes, a few static files, two test host identities and replacement certificate
pairs. All fixture private keys are deliberately public test credentials. The CA
signing key was discarded and is not supplied. The host's independent tests use
different inputs. No server source, parser, TLS event-loop wrapper, previous
implementation or comprehensive test suite is supplied.

The final runtime image must additionally provide pinned OpenSSL headers and API
documentation, libssl/libcrypto and their approved runtime dependencies. This
packet records the preparation environment's observed OpenSSL version only.
It does not claim those runtime mounts or dependency policies are implemented.

## Comparison with Stages 1–5

| Area | Current Stage 1–5 packet | Prepared Stage 10 draft |
|---|---|---|
| Starting code | None | None |
| Task scope | Selected complete stage, from static GET through plaintext operations | Complete HTTP/HTTPS/configuration/streaming/cache/worker contract |
| Source submission | One main.rs or main.cpp | Same single-source interface |
| Configuration | Flat key=value server.conf | nginx subset with contexts, inheritance, includes and documented toksec_* extensions |
| Dependencies | Standard library and approved OS calls | Same plus pinned OpenSSL C ABI for both languages |
| Runtime inputs | Config and static/upstream fixtures | Also certificate chains, leaf keys, CA certificate and reload generations |
| Visible feedback | Minimal ordinary smoke and provisional benchmarks | Plain bootstrap, config check, verified HTTPS GET, persistence and proxy smoke |
| Testing | Agent designs tests; comprehensive grader withheld | Same policy, expanded public obligations |
| Process model | Current measurements expect one server process | One master plus 1/2/4 workers with tree-wide limits |
| Resource accounting | One CPU, per-process 512 MiB address-space limit | 1/2/4-CPU profiles, 512 MiB aggregate charged memory, total descriptor limit |
| Release output | Controller-managed Git, periodic tags, last completed tag | Same; early plaintext tag allowed before complete TLS support |
| Final grade | API first; any required failure forfeits performance credit | Same; all mandatory TLS/worker checks are part of the gate |
| Run readiness | Existing v8 tools | Not implemented; proposal cannot be passed to current --level |

The memory accounting basis changes, not just the number of processes. Results
must identify the resource profile and must not be presented as direct v8
comparisons without controlling those differences.

## The first release and the final release are different gates

Bootstrap uses [bootstrap.conf](fixtures/config/bootstrap.conf), not the full
TLS/cache/worker example. A working plaintext GET can therefore establish a first
tag. Later tags must preserve previously passing visible checks. The agent chooses
which capability to implement and test next; examples do not impose a workflow.

Final grading extracts the last completed tag, rebuilds it independently and tests
the entire contract. An early tag with only plaintext GET receives whatever API
credit its behavior earns, but no full-stage performance credit. Numeric partial
credit and milestone weights are still undefined in the existing framework.

## Validation performed during preparation

OpenSSL generated four RSA-2048 leaf/key pairs for alpha.test and beta.test, with
two generations per name. Each leaf passed chain and hostname verification, its
public key matched its private key, and a wrong hostname failed verification.
The generation metadata and validity intervals are retained in
[fixture-metadata.json](fixtures/tls/fixture-metadata.json).

The packet inventory contains hashes and mount destinations. Documentation links
and instruction-preview assembly were checked. No nginx compatibility oracle,
candidate-server smoke test, TLS traffic benchmark or Stage 10 API suite has run.
Those checks cannot be replaced by successful certificate generation.

## Remaining delivery work

The next implementation units are versioned packet delivery, sandboxed TLS build
policy, process-tree enforcement/accounting, config/TLS/lifecycle API suites, and
calibrated performance drivers. Each needs independent verification before a
campaign. This applies the Sequence work into verifiable units principle to the
framework itself. A larger stage does not justify skipping its launch gates.
