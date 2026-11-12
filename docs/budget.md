# Pilot budget

The Level 1 Luna pilot admits at most 10,000,000 input-plus-output tokens and $5 of model inference at the pinned standard API rates. It counts cached input within input and reasoning within output. The token cap is conservative: at $0.50 per million, even an all-output run fits $5. Local compute, preparation, and subscription fees are excluded.

The price snapshot was verified on November 12, 2026 against [Luna's model page](https://developers.openai.com/api/docs/models/gpt-6-luna) and the [pricing table](https://developers.openai.com/api/docs/pricing). Standard rates per million tokens are $0.10 input, $0.01 cached input, $0.50 output, and $0.125 or $0.25 for cache writes depending on retention. The runner refuses requests above 64,000 input tokens, below the 272,000-token long-context threshold. Preflight refuses a price snapshot more than seven days old.

`metering.py` owns the durable ledger. Each request transitions from reserved to settled. A reservation includes the counted input and a 16,000-token output allowance, plus the worst applicable input cost. The runner uses the same model, history, and tool declarations for input counting and inference. It forces `service_tier="default"`, disables parallel tool calls, and enables no paid hosted tools.

Reported usage settles each reservation once. Cached and reasoning counters are retained separately for research. Dollar accounting is an upper bound at published rates because cache writes use the higher retention price. Missing cache-write details also use that upper rate for uncached input. This is not an invoice measurement.

A timeout, crash, missing usage, unexpected model, or changed service tier leaves unresolved reservations charged against the allowance. No automatic retries or restart are allowed. Incomplete responses with valid usage are settled, then stop. The accepted artifact survives failed or interrupted model calls. `result.json` reports the outcome, balance, and stop reason. Raw responses and the ledger stay in the ignored run directory.

## Authentication

The implemented runner uses the public Responses API with `OPENAI_API_KEY`. Credentials remain in the controller process and are never placed in prompts or candidate sandboxes.

`codex login status` confirms an existing ChatGPT login on the development host. It does not establish an API credential for this runner. Native Codex usage notifications can measure consumed tokens, but the native subagent launcher does not expose a hard per-request token cap.

The documented [ChatGPT-plan OAuth route](https://developers.openai.com/siwc/quickstart) requires application authorization for Responses scopes. Its [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) exclude `max_output_tokens`. That route is not implemented here. A future adapter could reserve a verified model-wide maximum for each request, but it must first verify input counting, output bounds, authorized model access, and accounting on that route. An API-equivalent dollar estimate must remain distinct from subscription billing.

The admission design follows [OpenAI's per-run spending controller](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api). Unit tests use synthetic provider responses and real sandbox evaluation. They do not constitute a live Luna result.
