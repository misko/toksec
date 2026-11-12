# Budget enforcement

The user authorized a Luna implementation run with a $5 limit. The available native subagent tool accepts a model and instructions, but does not expose a dollar ceiling or per-call usage settlement. Therefore this package does not launch the native agent under that authorization.

The native launcher also exposes no token-cap argument. Instructions to stop after a token count do not provide enforceable accounting. A controlled API loop can reserve counted input plus bounded output before each request to enforce an aggregate token allowance. Provider-specific accounting must be verified before treating that mechanism as a run limit.

The environment had no `OPENAI_API_KEY` configured during preparation. The API identifier, access, pricing, and accounting for the requested Luna model have not been verified. Native tool availability does not prove API availability.

A future metered adapter must reserve the maximum possible cost before each request, settle actual usage, and stop on uncertain charges. It must use standard processing, disable automatic retries, account for every model call, and preserve outstanding reservations after timeouts. The run must not exceed its shared $5 reservation ledger. Do not count reasoning tokens twice when the provider includes them in output usage.

Use exact decimal or rational currency arithmetic. Record the price schedule, input tokens, cached input, output, and any other charged categories. Do not enable paid hosted tools without including their charges. Enforce wall time and tool resources separately.

Official reference: [Build a per-run spending controller with the Responses API](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api).

This document describes requirements, not an implemented billing adapter. An uncapped native Luna run requires the user to explicitly change the budget constraint.
