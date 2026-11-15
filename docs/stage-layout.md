# Stage definitions and checker ownership

Edit shared requirements and stage definitions, then regenerate current packets.
Do not edit a historical run's copied inputs.

```text
RULES.md
contracts/artifact.schema.json
stages/
  common/
    ARTIFACTS.md
    INTERFACE.md
    HTTP.md
    BENCHMARK.md
    api.py
    smoke.py
    performance.py
  languages/{rust,cpp}.md
  capabilities/
  stage1/ ... stage5/
    SPEC.md
    profile.json
    api.py
    performance.py
  stage10/
    builder/
    fixtures/
    preview/
    host/
    input-manifest.json
tasks/v8/{rust,cpp}/
```

`toksec/specification.py` assembles the Stage 1–5 packet from shared rules, language
policy, selected requirements, minimal smoke descriptions, and workload parameters.
Both runners add the generated artifact contract and shared ownership instructions.
Their input assemblies do not include reference servers or test implementation fixtures.

Regenerate Stage 1–5 packets without model calls:

```sh
python3 -m toksec publish --output tasks/v8/rust --language rust
python3 -m toksec publish --output tasks/v8/cpp --language cpp
```

Stage 10 uses its separately versioned experimental packet and runtime. Its host
readiness and manifest files retain draft provenance. The operational runner notice
describes which parts are supported; full independent acceptance remains incomplete.
Do not silently replace its frozen policy with another stage's policy.

`evaluation/` contains executable checkers and calibration fixtures. Stage selections
reuse that code through `stages/common/` and `toksec/`. Builder submission tools run
only minimal visible smoke checks. Parent grading runs the selected independent
API suite and gates performance on correctness. Framework regression tests live in
`tests/`; they are not the server acceptance suite.

Reports belong under a run's `evaluation/<id>/` and publish separately from its
implementation. See [result storage](result-storage.md).
