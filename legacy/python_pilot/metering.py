"""Durable admission and usage accounting for one sequential builder."""

import json
import time
import uuid
from decimal import Decimal
from pathlib import Path

from .controller import locked
from toksec.storage import atomic_json
from toksec.metering import (MODEL, TOKEN_LIMIT, MAX_INPUT, MODEL_CONTEXT_LIMIT, MAX_OUTPUT,
                            RATES, PRICE_SOURCE, PRICE_DATE, tokens, usage_record, totals)


def read_ledger(run):
    return json.loads((Path(run) / "ledger.json").read_text())


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
