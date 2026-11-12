import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import controller
import metering
import runner
from capacity import budget_status
from test_controller import PARTIAL_SERVER

SERVER = PARTIAL_SERVER.replace("__CONTROLLER_PATH__", repr(str(controller.ROOT / "controller.py")))


def response(identity="response-1", input_count=100, output_count=50, cached=40, written=10, reasoning=20):
    return {"id": identity, "model": metering.MODEL, "service_tier": "default", "status": "completed",
            "output": [], "usage": {"input_tokens": input_count, "output_tokens": output_count,
            "total_tokens": input_count + output_count,
            "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": written},
            "output_tokens_details": {"reasoning_tokens": reasoning}}}


class MeteringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name) / "meter"
        controller.prepare(self.run)
        metering.initialize(self.run)

    def tearDown(self):
        self.temporary.cleanup()

    def test_usage_subsets_and_idempotent_settlement(self):
        identity = metering.reserve(self.run, 100)
        metering.settle(self.run, identity, response())
        metering.settle(self.run, identity, response())
        status = budget_status(self.run)
        self.assertEqual(status["tokens"]["used"], 150)
        self.assertEqual(status["tokens"]["remaining"], 9_999_850)
        self.assertEqual(Decimal(status["dollars"]["spent_upper_bound"]), Decimal("0.0000329"))
        self.assertTrue(status["can_start_model_call"])

    def test_pending_request_survives_restart_and_blocks_new_calls(self):
        metering.reserve(self.run, 100)
        self.assertEqual(metering.totals(metering.read_ledger(self.run))["reserved"], 16100)
        self.assertFalse(budget_status(self.run)["can_start_model_call"])
        with self.assertRaises(ValueError):
            metering.reserve(self.run, 100)
        with self.assertRaises(ValueError):
            metering.initialize(self.run)
        metering.stop(self.run, "timeout")
        self.assertEqual(metering.read_ledger(self.run)["state"], "uncertain")
        self.assertEqual(budget_status(self.run)["tokens"]["reserved"], 16100)

    def test_cap_refuses_before_dispatch(self):
        ledger = metering.read_ledger(self.run)
        ledger["token_limit"] = 16099
        controller.atomic_json(self.run / "ledger.json", ledger)
        with self.assertRaises(ValueError):
            metering.reserve(self.run, 100)
        self.assertEqual(metering.read_ledger(self.run)["requests"], [])

    def test_dollar_cap_and_request_size(self):
        ledger = metering.read_ledger(self.run)
        ledger["dollar_limit"] = "0.00001"
        controller.atomic_json(self.run / "ledger.json", ledger)
        with self.assertRaises(ValueError):
            metering.reserve(self.run, 100)
        for value in (64001, True, -1, 0.5):
            with self.assertRaises(ValueError):
                metering.reserve(self.run, value)

    def test_invalid_usage_retains_reservation(self):
        identity = metering.reserve(self.run, 100)
        invalid = response(input_count=101)
        with self.assertRaises(ValueError):
            metering.settle(self.run, identity, invalid)
        status = budget_status(self.run)
        self.assertEqual(status["accounting_status"], "uncertain")
        self.assertFalse(status["usage_complete"])
        self.assertEqual(status["tokens"]["used"], 0)
        self.assertEqual(status["tokens"]["reserved"], 16100)

    def test_incomplete_response_accounts_usage_then_stops(self):
        identity = metering.reserve(self.run, 100)
        incomplete = response()
        incomplete["status"] = "incomplete"
        metering.settle(self.run, identity, incomplete)
        status = budget_status(self.run)
        self.assertEqual(status["tokens"]["used"], 150)
        self.assertFalse(status["can_start_model_call"])

    def test_time_reserve_blocks_new_request(self):
        manifest = json.loads((self.run / "manifest.json").read_text())
        with patch("metering.time.time", return_value=manifest["started_unix"] + 841):
            with self.assertRaises(ValueError):
                metering.reserve(self.run, 100)

    def test_changed_model_or_tier_blocks_further_inference(self):
        identity = metering.reserve(self.run, 100)
        wrong_tier = response()
        wrong_tier["service_tier"] = "priority"
        with self.assertRaises(ValueError):
            metering.settle(self.run, identity, wrong_tier)
        with self.assertRaises(ValueError):
            metering.reserve(self.run, 100)

    def test_missing_cache_details_use_conservative_price(self):
        usage = response()["usage"]
        del usage["input_tokens_details"]
        actual = metering.usage_record(usage)
        self.assertEqual(Decimal(actual["cost_usd_upper_bound"]), Decimal("0.00005"))
        self.assertEqual(actual["total"], 150)

    def test_invalid_subsets_and_totals(self):
        for invalid in (response(cached=101), response(reasoning=51), response(written=-1)):
            with self.assertRaises(ValueError):
                metering.usage_record(invalid["usage"])
        invalid = response()["usage"]
        invalid["total_tokens"] = 999
        with self.assertRaises(ValueError):
            metering.usage_record(invalid)


class ScriptedClient:
    def __init__(self, fail_after_candidate=False):
        self.calls = []
        self.responses = 0
        self.fail_after_candidate = fail_after_candidate

    def post(self, endpoint, payload, timeout):
        self.calls.append((endpoint, payload))
        if endpoint.endswith("input_tokens"):
            return {"input_tokens": 100}
        self.responses += 1
        if self.responses == 2 and self.fail_after_candidate:
            raise TimeoutError("synthetic timeout")
        result = response(identity=f"response-{self.responses}")
        name, args = ("submit_candidate", {"source": SERVER}) if self.responses == 1 else ("finish", {})
        result["output"] = [{"type": "function_call", "id": f"fc-{self.responses}",
                             "call_id": f"call-{self.responses}", "name": name, "arguments": json.dumps(args)}]
        return result


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name) / "runner"
        controller.prepare(self.run)

    def tearDown(self):
        self.temporary.cleanup()

    def test_tool_loop_uses_real_sandbox_and_exports_checkpoint(self):
        client = ScriptedClient()
        result = runner.run_loop(self.run, client)
        self.assertTrue(result["exported"])
        self.assertEqual(result["outcome"], "working_partial")
        self.assertEqual(result["capacity"]["tokens"]["used"], 300)
        self.assertEqual((Path(result["artifact"]) / "server.py").read_text(), SERVER)
        for index in (0, 2):
            counted = client.calls[index][1]
            generated = client.calls[index + 1][1]
            for key in ("model", "input", "tools"):
                self.assertEqual(counted[key], generated[key])
            self.assertEqual(generated["service_tier"], "default")
            self.assertEqual(generated["max_output_tokens"], 16000)

    def test_timeout_keeps_candidate_and_reservation_without_retry(self):
        client = ScriptedClient(fail_after_candidate=True)
        result = runner.run_loop(self.run, client)
        self.assertTrue(result["exported"])
        self.assertEqual(client.responses, 2)
        self.assertEqual(result["capacity"]["tokens"]["used"], 150)
        self.assertEqual(result["capacity"]["tokens"]["reserved"], 16100)
        self.assertEqual(result["capacity"]["accounting_status"], "uncertain")

    def test_preflight_missing_key_makes_no_requests(self):
        with patch.dict("os.environ", {}, clear=True):
            status = runner.preflight(self.run)
        self.assertFalse(status["launch_allowed"])
        self.assertFalse((self.run / "ledger.json").exists())

    def test_tool_cannot_select_path_or_execute_host_shell(self):
        for name, args in (("shell", {"command": "true"}), ("submit_candidate", {"source": "", "path": "/tmp/other"}),
                           ("budget_status", {"tokens": 999}), ("finish", {"run": "/tmp/other"})):
            with self.assertRaises(ValueError):
                runner.dispatch(self.run, name, args)
