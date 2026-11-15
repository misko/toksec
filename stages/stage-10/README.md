# Stage 10 inputs and specification

This is the canonical input directory for the Stage 10 experiment. It contains
stage-specific instructions and fixtures used by the
[regular runner’s Stage 10 backend](../../stage10/README.md). A Terra campaign has
completed; its [implementation and partial evaluation](../../results/stage-10/cpp/README.md)
are preserved. The full acceptance evaluator remains incomplete.
[Host readiness](host/READINESS.md) and `input-manifest.json` preserve the original
preparation checklist. Their readiness flags are historical, not the current
runner status. The relocation preserves builder files, previews, and fixture bytes;
historical run packets remain unchanged.

## What the agent receives

[packet.py](packet.py) assembles the current packet from the canonical root
[RULES.md](../../RULES.md), shared [ARTIFACTS.md](../common/ARTIFACTS.md), START,
INTERFACE, the selected language policy, HTTP, CONFIGURATION, TLS, OPERATIONS,
BENCHMARK, and SMOKE. The runner supplies the same allowlisted documents through
its input tool, plus the generated artifact contract and operational budget notice.
The old `builder/RULES.md` and `preview/` packets are preserved historical drafts;
they are not the source of current shared policy. Generate a current preview with
`python3 -m toksec publish --stage 10 --language cpp --output OUTPUT`.

The agent also receives a minimal bootstrap configuration, a full example with
includes, a few static files, two test host identities and replacement certificate
pairs. All fixture private keys are deliberately public test credentials. The CA
signing key was discarded and is not supplied. The host's independent tests use
different inputs. No server source, parser, TLS event-loop wrapper, previous
implementation or comprehensive test suite is supplied.

The runner provides approved OpenSSL headers, libssl/libcrypto, and constrained
build/runtime sandboxes. Run manifests record the installed toolchain. This packet
retains the preparation environment's original OpenSSL metadata.

## Comparison with Stages 1–5

| Area | Current Stage 1–5 packet | Current Stage 10 |
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
| Run readiness | Existing v8 tools | Regular `toksec` / `evaluate.py`; partial API, provisional performance |

The memory accounting basis changes, not just the number of processes. Results
must identify the resource profile and must not be presented as direct v8
comparisons without controlling those differences.

## The first release and the final release are different gates

Bootstrap uses [bootstrap.conf](fixtures/config/bootstrap.conf), not the full
TLS/cache/worker example. A working plaintext GET can therefore establish a first
tag. Later tags must preserve previously passing visible checks. The agent chooses
which capability to implement and test next; examples do not impose a workflow.

Final grading extracts the last completed tag and rebuilds it independently. The
current independent checker covers part of the contract; full acceptance requires
the remaining tests. An early tag with only plaintext GET receives whatever API
credit its behavior earns, but no full-stage performance credit. Numeric partial
credit and milestone weights are still undefined in the existing framework.

## Historical preparation validation

OpenSSL generated four RSA-2048 leaf/key pairs for alpha.test and beta.test, with
two generations per name. Each leaf passed chain and hostname verification, its
public key matched its private key, and a wrong hostname failed verification.
The generation metadata and validity intervals are retained in
[fixture-metadata.json](fixtures/tls/fixture-metadata.json).

The packet inventory contains hashes and mount destinations. Documentation links
and instruction-preview assembly were checked. No nginx compatibility oracle,
candidate-server smoke test, TLS traffic benchmark or Stage 10 API suite has run.
Those checks cannot be replaced by successful certificate generation.

## Remaining acceptance work

The experimental runner implements packet delivery, approved TLS compilation,
process-tree enforcement, tagged releases, and partial API checks. Full
configuration, TLS, and lifecycle coverage and calibrated performance drivers
remain incomplete. See the runner README for the current supported profile.
