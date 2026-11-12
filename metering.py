"""Durable admission and usage accounting for one sequential builder."""

import json
import time
import uuid
from decimal import Decimal
from pathlib import Path

from controller import atomic_json, locked


MODEL = "gpt-6-luna"
TOKEN_LIMIT = 10_000_000
MAX_INPUT = 64_000
MODEL_CONTEXT_LIMIT = 1_050_000
MAX_OUTPUT = 16_000
RATES = {"input": "0.10", "cached": "0.01", "write_upper": "0.25", "output": "0.50"}
PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-luna"
PRICE_DATE = "2026-11-12"


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


def read_ledger(run):
    return json.loads((Path(run) / "ledger.json").read_text())


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


def initialize(run):
    run = Path(run).resolve()
    with locked(run):
        manifest = json.loads((run / "manifest.json").read_text())
        config = manifest["configuration"]
        if (run / "ledger.json").exists() or manifest["started_unix"] is not None:
            raise ValueError("run already started; prepare a fresh run")
        if (config["model"] != MODEL or config["service_tier"] != "default"
                or config["budget_usd"] != "5.00" or config["token_limit"] != TOKEN_LIMIT):
            raise ValueError("this pilot supports only standard Luna with a $5 cap")
        ledger = {"schema_version": 1, "state": "active", "reason": None,
                  "model": MODEL, "service_tier": "default", "dollar_limit": "5.00",
                  "token_limit": TOKEN_LIMIT, "rates_usd_per_million": RATES,
                  "price_source": PRICE_SOURCE, "price_verified_date": PRICE_DATE,
                  "requests": []}
        atomic_json(run / "ledger.json", ledger)
        manifest.update(started_unix=time.time(), backend="responses_api",
                        model_calls=None, model_spend_usd=None, accounting_source="ledger.json")
        atomic_json(run / "manifest.json", manifest)


def reserve(run, input_count):
    input_count = tokens(input_count)
    if input_count > MAX_INPUT:
        raise ValueError("request exceeds the pilot input limit")
    run = Path(run).resolve()
    with locked(run):
        ledger = read_ledger(run)
        manifest = json.loads((run / "manifest.json").read_text())
        config = manifest["configuration"]
        if ledger["state"] != "active" or any(r["state"] == "reserved" for r in ledger["requests"]):
            raise ValueError("run stopped or an earlier request has unresolved usage")
        if time.time() >= manifest["started_unix"] + config["wall_seconds"] - config["reserve_seconds"]:
            raise ValueError("validation reserve reached")
        balance = totals(ledger)
        reservation = MODEL_CONTEXT_LIMIT + MAX_OUTPUT
        dollars = (Decimal(MODEL_CONTEXT_LIMIT) * Decimal(RATES["write_upper"]) * 2
                   + Decimal(MAX_OUTPUT) * Decimal(RATES["output"]) * Decimal("1.5")) / 1_000_000
        if reservation > balance["remaining"] or dollars > Decimal(balance["remaining_usd"]):
            raise ValueError("insufficient remaining budget for the next request")
        request_id = uuid.uuid4().hex
        ledger["requests"].append({"id": request_id, "state": "reserved", "input_bound": MODEL_CONTEXT_LIMIT,
                                   "counted_input": input_count,
                                   "output_bound": MAX_OUTPUT, "reserved_tokens": reservation,
                                   "reserved_usd": str(dollars), "reserved_unix": time.time()})
        atomic_json(run / "ledger.json", ledger)
        return request_id


def settle(run, request_id, response):
    run = Path(run).resolve()
    with locked(run):
        ledger = read_ledger(run)
        entry = next(r for r in ledger["requests"] if r["id"] == request_id)
        try:
            record = usage_record(response["usage"])
            if entry["state"] == "settled":
                if entry["response_id"] == response["id"] and entry["usage"] == record:
                    return record
                raise ValueError("conflicting settlement")
            if response["model"] != MODEL or response["service_tier"] != "default":
                raise ValueError("unexpected response model or service tier")
            if any(r.get("response_id") == response["id"] for r in ledger["requests"]):
                raise ValueError("response already accounted for")
            if (record["input"] > MODEL_CONTEXT_LIMIT or record["total"] > entry["reserved_tokens"]
                    or record["output"] > entry["output_bound"]
                    or Decimal(record["cost_usd_upper_bound"]) > Decimal(entry["reserved_usd"])):
                raise ValueError("reported usage exceeded reservation")
            entry.update(state="settled", response_id=response["id"], usage=record,
                         response_status=response["status"], settled_unix=time.time())
            if response["status"] != "completed" or record["input"] > MAX_INPUT:
                ledger.update(state="stopped", reason="incomplete response or actual input exceeds pilot limit")
        except (KeyError, TypeError, ValueError) as error:
            ledger.update(state="uncertain", reason=str(error))
            atomic_json(run / "ledger.json", ledger)
            raise ValueError("usage cannot be settled; run blocked") from error
        atomic_json(run / "ledger.json", ledger)
        return record


def stop(run, reason):
    run = Path(run).resolve()
    with locked(run):
        ledger = read_ledger(run)
        pending = any(r["state"] == "reserved" for r in ledger["requests"])
        ledger.update(state="uncertain" if pending or ledger["state"] == "uncertain" else "stopped", reason=reason)
        atomic_json(run / "ledger.json", ledger)
