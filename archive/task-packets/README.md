# Generated task packets

`v8/rust/` and `v8/cpp/` are the current Stage 1–5 generated packets. Edit `RULES.md`
and `stages/`, then regenerate with `python3 -m toksec publish --language LANGUAGE
--output tasks/v8/LANGUAGE`. Do not edit generated packets directly.

Versions v2–v7 are historical snapshots. Their presence does not select a runtime
or authorize a campaign. Keep them for historical inspection; reproduce old runs
with their recorded checkout. The original Python pilot task moved intact to
`legacy/python_pilot/tasks/http/` with its runtime.

Stage 10 uses its separately assembled experimental input packet under
`stages/stage10/`. It is not a complete Stage 1–5-style accepted profile.
