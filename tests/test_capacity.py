import json
import tempfile
import unittest
from pathlib import Path

import controller
from capacity import TOOL_SPEC, bind_budget_status, budget_status


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run = Path(self.temporary.name) / "capacity"
        controller.prepare(self.run)

    def tearDown(self):
        self.temporary.cleanup()

    def start(self, timestamp):
        path = self.run / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["started_unix"] = timestamp
        manifest["model_calls"] = 1
        controller.atomic_json(path, manifest)

    def test_prepared_capacity_is_known_but_cannot_authorize_launch(self):
        result = budget_status(self.run, now=100)
        self.assertEqual(result["dollars"]["remaining"], "5.00")
        self.assertIsNone(result["time"]["remaining_seconds"])
        self.assertIsNone(result["tokens"]["remaining"])
        self.assertIsNone(result["context_window"]["remaining_tokens"])
        self.assertFalse(result["can_start_model_call"])

    def test_running_without_meter_does_not_claim_known_spend(self):
        self.start(100)
        result = budget_status(self.run, now=200)
        self.assertEqual(result["accounting_status"], "unavailable")
        self.assertIsNone(result["dollars"]["spent"])
        self.assertIsNone(result["dollars"]["remaining"])
        self.assertEqual(result["time"]["remaining_seconds"], 800)
        self.assertEqual(result["time"]["work_seconds_remaining"], 740)

    def test_validation_reserve_and_exhausted_clock(self):
        self.start(100)
        result = budget_status(self.run, now=950)
        self.assertEqual(result["time"]["remaining_seconds"], 50)
        self.assertEqual(result["time"]["work_seconds_remaining"], 0)
        self.assertEqual(budget_status(self.run, now=1100)["time"]["remaining_seconds"], 0)

    def test_invalid_clock_is_rejected(self):
        self.start(100)
        for value in (99, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                budget_status(self.run, now=value)

    def test_model_cannot_change_run_or_budget_and_reads_do_not_mutate(self):
        handle = bind_budget_status(self.run)
        before = (self.run / "manifest.json").read_bytes()
        for args in ({"run": "/another/run"}, {"remaining": 100}, None, []):
            with self.assertRaises(ValueError):
                handle(args)
        self.assertEqual(handle({})["run_id"], "capacity")
        self.assertEqual((self.run / "manifest.json").read_bytes(), before)
        self.assertFalse(TOOL_SPEC["parameters"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
