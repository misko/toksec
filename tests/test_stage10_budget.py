import concurrent.futures
import tempfile
import threading
import unittest
from pathlib import Path

from stage10.budget import BudgetError, BudgetLedger, MAX_INPUT_TOKENS, MODEL


def request():
    return {"model": MODEL, "input": [{"role": "user", "content": "build"}],
            "service_tier": "default", "store": False, "truncation": "disabled",
            "reasoning": {"effort": "medium"}, "max_output_tokens": 20_000,
            "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
            "tools": [{"type": "function", "name": "finish", "description": "finish",
                       "strict": True, "parameters": {"type": "object", "properties": {},
                                                       "additionalProperties": False}}]}


def count(inputs=32_000):
    return lambda body: {"object": "response.input_tokens", "input_tokens": inputs}


def response(inputs=32_000, outputs=20_000):
    return {"model": MODEL, "service_tier": "default", "status": "completed",
            "usage": {"input_tokens": inputs, "output_tokens": outputs}}


class Stage10BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite"

    def test_exact_boundary_reserves_before_send_and_settles(self):
        ledger = BudgetLedger(self.path, "0.23")
        def send(body):
            report = BudgetLedger(self.path, "0.23").report()
            self.assertEqual(report["held_nanodollars"], 230_000_000)
            self.assertTrue(report["blocked"])
            self.assertEqual(body, request())
            return response()
        ledger.execute(request(), count(), send)
        report = ledger.report()
        self.assertEqual(report["spent_nanodollars"], 140_000_000)
        self.assertEqual(report["held_nanodollars"], 0)
        self.assertEqual(len(report["requests"][0]["request_hash"]), 64)
        with self.assertRaises(BudgetError):
            ledger.execute(request(), count(), lambda _: self.fail("must not send"))

    def test_count_payload_has_all_input_fields_without_generation_controls(self):
        ledger = BudgetLedger(self.path)
        body = request()
        body["instructions"] = "instructions"
        def provider_count(payload):
            self.assertEqual(payload, {k: v for k, v in body.items() if k in
                                      {"model", "input", "instructions", "tools", "reasoning", "truncation"}})
            return count()(payload)
        ledger.execute(body, provider_count, lambda _: response())

    def test_over_input_cap_never_sends(self):
        ledger = BudgetLedger(self.path)
        with self.assertRaises(BudgetError):
            ledger.execute(request(), count(MAX_INPUT_TOKENS+1), lambda _: self.fail("sent"))
        self.assertEqual(ledger.report()["requests"], [])

    def test_uncertain_charge_persists_and_no_automatic_retry(self):
        ledger = BudgetLedger(self.path)
        calls = []
        def fail(_):
            calls.append(1)
            raise TimeoutError("unknown remote completion")
        with self.assertRaises(TimeoutError):
            ledger.execute(request(), count(), fail)
        reopened = BudgetLedger(self.path)
        with self.assertRaises(BudgetError):
            reopened.execute(request(), count(), fail)
        self.assertEqual(len(calls), 1)
        self.assertEqual(reopened.report()["held_nanodollars"], 230_000_000)

    def test_cumulative_two_dollar_admission_never_overshoots(self):
        ledger = BudgetLedger(self.path)
        calls = []
        def send(_):
            calls.append(1)
            report = ledger.report()
            self.assertLessEqual(report["spent_nanodollars"] + report["held_nanodollars"],
                                 2_000_000_000)
            return response()
        for _ in range(13):
            ledger.execute(request(), count(), send)
        with self.assertRaises(BudgetError):
            ledger.execute(request(), count(), send)
        self.assertEqual(len(calls), 13)
        self.assertEqual(ledger.report()["spent_nanodollars"], 1_820_000_000)

    def test_transport_mutation_holds_reservation(self):
        ledger = BudgetLedger(self.path)
        def mutate(body):
            body["max_output_tokens"] = 20001
            return response()
        with self.assertRaises(BudgetError):
            ledger.execute(request(), count(), mutate)
        self.assertTrue(ledger.report()["blocked"])

    def test_concurrent_callers_cannot_send_while_reservation_pending(self):
        entered, release = threading.Event(), threading.Event()
        ledger = BudgetLedger(self.path)
        def send(_):
            entered.set()
            self.assertTrue(release.wait(5))
            return response()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(ledger.execute, request(), count(), send)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(BudgetError):
                    BudgetLedger(self.path).execute(request(), count(), lambda _: self.fail("second send"))
            finally:
                release.set()
            first.result(timeout=5)

    def test_mutated_count_payload_or_original_is_rejected(self):
        for target in ("count", "original"):
            with self.subTest(target=target):
                ledger = BudgetLedger(self.path)
                body = request()
                def mutate(payload):
                    (payload if target == "count" else body)["input"][0]["content"] = "changed"
                    return count()(payload)
                with self.assertRaises(BudgetError):
                    ledger.execute(body, mutate, lambda _: self.fail("sent changed input"))
                self.assertEqual(ledger.report()["requests"], [])

    def test_bad_usage_or_provider_mismatch_holds_reservation(self):
        cases = [None, response(32001), response(outputs=20001),
                 {**response(), "service_tier": "priority"},
                 {**response(), "model": "other"}, {**response(), "usage": None},
                 {**response(), "status": "in_progress"}]
        for i, result in enumerate(cases):
            with self.subTest(result=result):
                ledger = BudgetLedger(self.path.parent / f"case{i}.sqlite")
                with self.assertRaises(BudgetError):
                    ledger.execute(request(), count(), lambda _, r=result: r)
                self.assertTrue(ledger.report()["blocked"])
                self.assertEqual(ledger.report()["held_nanodollars"], 230_000_000)

    def test_incomplete_response_with_valid_usage_is_charged(self):
        ledger = BudgetLedger(self.path)
        ledger.execute(request(), count(), lambda _: {**response(), "status": "incomplete"})
        self.assertFalse(ledger.report()["blocked"])
        self.assertEqual(ledger.report()["spent_nanodollars"], 140_000_000)

    def test_rejects_unbounded_and_hidden_request_features(self):
        changes = [{"previous_response_id": "resp_x"}, {"conversation": "x"},
                   {"service_tier": "auto"}, {"max_output_tokens": 20001},
                   {"max_output_tokens": True}, {"reasoning": {"effort": "max"}},
                   {"tools": [{"type": "web_search"}]},
                   {"input": [{"type": "reasoning", "encrypted_content": "hidden"}]},
                   {"prompt_cache_options": {"mode": "implicit", "ttl": "12h"}}]
        ledger = BudgetLedger(self.path)
        for change in changes:
            with self.subTest(change=change), self.assertRaises(BudgetError):
                ledger.execute({**request(), **change}, lambda _: self.fail("counted"), lambda _: self.fail("sent"))

    def test_ledger_limit_and_prices_cannot_change_on_reopen(self):
        BudgetLedger(self.path)
        with self.assertRaises(BudgetError):
            BudgetLedger(self.path, "1")
        with self.assertRaises(BudgetError):
            BudgetLedger(self.path, prices={"input": 1})
        with self.assertRaises(BudgetError):
            BudgetLedger(self.path, "2.01")

    def test_fractional_and_heuristic_counts_are_rejected(self):
        ledger = BudgetLedger(self.path)
        for result in (32000, {"input_tokens": 32000},
                       {"object": "response.input_tokens", "input_tokens": 3.2},
                       {"object": "response.input_tokens", "input_tokens": True}):
            with self.subTest(result=result), self.assertRaises(BudgetError):
                ledger.execute(request(), lambda _, r=result: r, lambda _: self.fail("sent"))


if __name__ == "__main__":
    unittest.main()
