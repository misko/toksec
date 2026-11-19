# Artifact contracts

`artifact.schema.json` defines builder source filenames, encoding, size bounds,
and release ownership. Both runners generate and freeze a matching `artifact.json`.
`evaluation.schema.json` defines parent-owned grading records and their provenance.
Validation lives in `toksec/artifacts.py`.

The schemas support stage identities 1–16. This does not mean every stage has a
runnable profile: Stages 1–5 are implemented and Stage 10 remains experimental.
Stages 6–9 are proposed. See the [stage layout](../docs/stage-layout.md) and
[result workflow](../docs/result-storage.md).

`security-evaluation.schema.json` defines parent security analyses with
`kind: "security"`. It requires exact release provenance and an artifact inventory.
The shared validator dispatches this kind separately from API/performance records.
Security status describes analysis completion, not stage acceptance or a guarantee
of security. See the [recording workflow](../docs/result-storage.md#security-evaluations).
