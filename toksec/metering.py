"""Shared token accounting and pinned rates; campaign admission owns ledger I/O."""

from decimal import Decimal


MODEL = "gpt-6-luna"
TOKEN_LIMIT = 10_000_000
MAX_INPUT = 64_000
MODEL_CONTEXT_LIMIT = 1_050_000
MAX_OUTPUT = 16_000
RATES = {"input": "0.10", "cached": "0.01", "write_upper": "0.25", "output": "0.50"}
PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-luna"
# Standard, nonregional pricing verified against the provider's model and pricing pages.
PRICE_DATE = "2026-11-20"


def tokens(value):
    if type(value) is not int or value < 0:
        raise ValueError("token counts must be nonnegative integers")
    return value


def usage_record(usage, rates=None):
    rates = RATES if rates is None else rates
    input_count = tokens(usage["input_tokens"])
    output_count = tokens(usage["output_tokens"])
    details = usage.get("input_tokens_details") or {}
    cached = tokens(details.get("cached_tokens", 0))
    written = tokens(details.get("cache_write_tokens", 0))
    reasoning = tokens((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0))
    if cached + written > input_count or reasoning > output_count:
        raise ValueError("usage subsets exceed their totals")
    total = input_count + output_count
    if tokens(usage["total_tokens"]) != total:
        raise ValueError("inconsistent total token usage")
    ordinary_rate = rates["input"] if "cache_write_tokens" in details else rates["write_upper"]
    input_multiplier = Decimal(2 if input_count > 272_000 else 1)
    output_multiplier = Decimal("1.5" if input_count > 272_000 else "1")
    cost = ((Decimal(input_count - cached - written) * Decimal(ordinary_rate)
            + Decimal(cached) * Decimal(rates["cached"])
            + Decimal(written) * Decimal(rates["write_upper"])) * input_multiplier
            + Decimal(output_count) * Decimal(rates["output"]) * output_multiplier) / 1_000_000
    return {"input": input_count, "cached_input": cached, "cache_write": written,
            "output": output_count, "reasoning": reasoning, "total": total,
            "cost_usd_upper_bound": str(cost)}


def totals(ledger):
    settled = [r for r in ledger["requests"] if r["state"] == "settled"]
    pending = [r for r in ledger["requests"] if r["state"] == "reserved"]
    used = sum(r["usage"]["total"] for r in settled)
    reserved = sum(r["reserved_tokens"] for r in pending)
    spent = sum((Decimal(r["usage"]["cost_usd_upper_bound"]) for r in settled), Decimal(0))
    dollars_reserved = sum((Decimal(r["reserved_usd"]) for r in pending), Decimal(0))
    return {"used": used, "reserved": reserved, "remaining": ledger["token_limit"] - used - reserved,
            "spent_usd_upper_bound": str(spent), "reserved_usd": str(dollars_reserved),
            "remaining_usd": str(Decimal(ledger["dollar_limit"]) - spent - dollars_reserved)}
