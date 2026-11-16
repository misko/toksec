"""Fail-closed, durable admission for a small, stateless Responses workload.

Trust boundary: count_tokens must call the provider's /responses/input_tokens;
send must send the supplied body once, without automatic retries or additions,
to the standard, nonregional OpenAI endpoint. Neither callback is an estimator.
Provider pricing and enforcement are assumptions, not a local billing firewall.

Official references (verified 2026-11-15):
https://developers.openai.com/api/docs/guides/token-counting
https://developers.openai.com/api/docs/models/gpt-6.1-terra
https://developers.openai.com/api/reference/resources/responses/methods/create

The count endpoint includes framing. max_output_tokens includes reasoning.
Only explicit text history and local function schemas are admitted: no server
conversation, encrypted reasoning, remote content, or billable hosted tools.
"""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

MODEL = "gpt-6.1-terra"
PRICE_DATE = "2026-11-15"
MAX_INPUT_TOKENS = 32_000
MAX_OUTPUT_TOKENS = 20_000
# Nanodollars per token. Reserve worst 30-minute cache-write input at 2x,
# output at 1.5x; settlement conservatively treats every input as a cache write.
PRICES = {"input": 1000, "cached_input": 50, "cache_write": 1250, "output": 5000}
RESERVED_INPUT = 2500
RESERVED_OUTPUT = 7500
COUNT_FIELDS = frozenset({"model", "input", "instructions", "tools", "reasoning",
                          "parallel_tool_calls", "tool_choice", "truncation"})
SEND_FIELDS = COUNT_FIELDS | {"max_output_tokens", "service_tier", "store", "prompt_cache_options"}


class BudgetError(RuntimeError):
    """Admission was denied; no further generation is authorized."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise BudgetError(f"{name} must be a nonnegative integer")
    return value


def validate_request(body):
    if not isinstance(body, dict) or set(body) - SEND_FIELDS:
        raise BudgetError("unsupported request fields")
    required = {"model": MODEL, "service_tier": "default", "store": False,
                "truncation": "disabled", "reasoning": {"effort": "medium"},
                "prompt_cache_options": {"mode": "implicit", "ttl": "30m"}}
    if any(body.get(key) != value for key, value in required.items()):
        raise BudgetError("model, tier, storage, truncation, or reasoning mismatch")
    cap = _integer(body.get("max_output_tokens"), "max_output_tokens")
    if not 1 <= cap <= MAX_OUTPUT_TOKENS:
        raise BudgetError("output cap exceeds profile")
    if "instructions" in body and not isinstance(body["instructions"], str):
        raise BudgetError("instructions must be text")
    history = body.get("input")
    if not isinstance(history, str):
        if not isinstance(history, list) or not history:
            raise BudgetError("explicit text history required")
        for item in history:
            if (not isinstance(item, dict) or set(item) != {"role", "content"}
                    or item["role"] not in {"system", "developer", "user", "assistant"}
                    or not isinstance(item["content"], str)):
                raise BudgetError("history must contain only plain role/content text")
    if "parallel_tool_calls" in body and type(body["parallel_tool_calls"]) is not bool:
        raise BudgetError("invalid parallel_tool_calls")
    if body.get("tool_choice", "auto") not in ("auto", "none", "required"):
        raise BudgetError("unsupported tool choice")
    functions = body.get("tools", [])
    if not isinstance(functions, list):
        raise BudgetError("tools must be a list")
    names = set()
    for tool in functions:
        if (not isinstance(tool, dict)
                or set(tool) != {"type", "name", "description", "strict", "parameters"}
                or tool["type"] != "function" or tool["strict"] is not True
                or not isinstance(tool["name"], str) or not tool["name"]
                or not isinstance(tool["description"], str)
                or not isinstance(tool["parameters"], dict)
                or tool["name"] in names):
            raise BudgetError("only strict local function schemas are allowed")
        names.add(tool["name"])


class BudgetLedger:
    """One ledger is the entire authorized run; never create one per request.

    execute(body, provider_count, single_send) is the only admission API.
    A pending/uncertain request permanently prevents a later send, including
    after process death. There is deliberately no release/retry/reset method.
    """

    def __init__(self, path, limit_usd="2", *, prices=None):
        amount = Decimal(str(limit_usd)) * 1_000_000_000
        if not amount.is_finite() or amount <= 0 or amount > 5_000_000_000 or amount != int(amount):
            raise BudgetError("limit must be positive, precise, and at most $5")
        if prices is not None and prices != PRICES:
            raise BudgetError("unverified price schedule")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limit = int(amount)
        self.config = _canonical({"version": 1, "limit": self.limit, "model": MODEL,
                                  "prices": PRICES, "input_cap": MAX_INPUT_TOKENS,
                                  "output_cap": MAX_OUTPUT_TOKENS, "tier": "default"})
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, count_hash TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_cap INTEGER NOT NULL, reserved INTEGER NOT NULL, debit INTEGER, status TEXT NOT NULL, detail TEXT, usage TEXT)")
            db.execute("INSERT OR IGNORE INTO config VALUES (1, ?)", (self.config,))
            self._check_config(db)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _check_config(self, db):
        if db.execute("SELECT value FROM config WHERE id=1").fetchone() != (self.config,):
            raise BudgetError("ledger configuration mismatch")

    def report(self):
        with self._db() as db:
            self._check_config(db)
            rows = db.execute("SELECT id, request_hash, count_hash, input_tokens, output_cap, reserved, debit, status, detail, usage FROM requests ORDER BY rowid").fetchall()
        keys = ("id", "request_hash", "count_hash", "input_tokens", "output_cap", "reserved_nanodollars", "debit_nanodollars", "status", "detail", "usage")
        spent = sum(row[6] or 0 for row in rows)
        held = sum(row[5] for row in rows if row[7] != "settled")
        return {"limit_nanodollars": self.limit, "spent_nanodollars": spent,
                "held_nanodollars": held, "remaining_nanodollars": self.limit-spent-held,
                "blocked": any(row[7] != "settled" for row in rows),
                "requests": [dict(zip(keys, row)) for row in rows]}

    def execute(self, body, count_tokens, send):
        validate_request(body)
        serialized = _canonical(body)
        frozen = json.loads(serialized)
        count_body = {key: value for key, value in frozen.items() if key in COUNT_FIELDS}
        count_serialized = _canonical(count_body)
        if self.report()["blocked"]:
            raise BudgetError("unsettled request blocks generation")
        count = count_tokens(count_body)
        if _canonical(count_body) != count_serialized or _canonical(body) != serialized:
            raise BudgetError("request mutated during counting")
        if not isinstance(count, dict) or count.get("object") != "response.input_tokens":
            raise BudgetError("provider token-count response required")
        inputs = _integer(count.get("input_tokens"), "input_tokens")
        if inputs > MAX_INPUT_TOKENS:
            raise BudgetError("provider count exceeds input cap")
        cap = frozen["max_output_tokens"]
        reserve = inputs * RESERVED_INPUT + cap * RESERVED_OUTPUT
        request_id = uuid.uuid4().hex
        with self._db() as db:
            self._check_config(db)
            if db.execute("SELECT 1 FROM requests WHERE status != 'settled'").fetchone():
                raise BudgetError("unsettled request blocks generation")
            spent = db.execute("SELECT COALESCE(SUM(debit),0) FROM requests").fetchone()[0]
            if spent + reserve > self.limit:
                raise BudgetError("insufficient budget for full request reservation")
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', NULL, NULL)",
                       (request_id, hashlib.sha256(serialized.encode()).hexdigest(),
                        hashlib.sha256(count_serialized.encode()).hexdigest(), inputs, cap, reserve))
        # The reservation is committed before crossing the network boundary.
        outbound = json.loads(serialized)
        try:
            response = send(outbound)
            if _canonical(outbound) != serialized:
                raise BudgetError("transport mutated the reserved request")
            debit, usage = self._settlement(response, inputs, cap, reserve)
        except BaseException as exc:
            with self._db() as db:
                db.execute("UPDATE requests SET status='uncertain', detail=? WHERE id=?",
                           (type(exc).__name__, request_id))
            raise
        with self._db() as db:
            self._check_config(db)
            db.execute("UPDATE requests SET status='settled', debit=?, usage=? WHERE id=? AND status='pending'",
                       (debit, _canonical(usage), request_id))
        return response

    @staticmethod
    def _settlement(response, counted, cap, reserve):
        if not isinstance(response, dict) or response.get("model") != MODEL or response.get("service_tier") != "default":
            raise BudgetError("response model/tier mismatch")
        if response.get("status") not in {"completed", "incomplete"}:
            raise BudgetError("response is not terminal")
        usage = response.get("usage")
        if not isinstance(usage, dict):
            raise BudgetError("missing usage")
        inputs = _integer(usage.get("input_tokens"), "usage input_tokens")
        outputs = _integer(usage.get("output_tokens"), "usage output_tokens")
        if inputs != counted or outputs > cap:
            raise BudgetError("provider violated counted input or output bound")
        # No cache discounts are reclaimed: this is a conservative debit, not an invoice.
        debit = inputs * PRICES["cache_write"] + outputs * PRICES["output"]
        if debit > reserve:
            raise BudgetError("provider charge exceeds reservation")
        return debit, usage
