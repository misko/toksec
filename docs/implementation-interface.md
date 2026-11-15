# Implementation interface: Stages 1 and 2

Both independent builders start without code. They submit one main.rs and receive
bounded controller tools for compilation, testing, measurement and Git releases.

Authoritative sources:

- [Shared executable interface](../stages/common/INTERFACE.md): source, build, process, configuration and resource limits.
- [Shared rules](../RULES.md): tags, partial credit, API-first grading and capacity.
- [Common HTTP requirements](../stages/common/HTTP.md).
- [Stage 1 contract](../stages/stage-01/SPEC.md) and [Stage 2 contract](../stages/stage-02/SPEC.md).
- [Input and suite layout](stage-layout.md): exactly what goes into model context and what remains host-side.
- [CLI walkthrough](cli-walkthrough.md): evaluating a source file or the last completed Git tag.

Generated tasks/v5 packets include the complete required configuration and selected
workload matrix. Checker source is not included in the builder prompt.
