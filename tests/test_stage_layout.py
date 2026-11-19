import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toksec import campaign, controller
from toksec.evaluate import evaluate
from toksec.specification import packet, specification, workloads


class StageLayoutTests(unittest.TestCase):
    def test_independent_contracts_and_workloads(self):
        for level in (1, 2):
            text = packet(level)
            self.assertEqual(text.count('# Shared builder rules'), 1)
            self.assertNotIn('def run_checks', text)
            self.assertIn('No starter code', text)
        self.assertNotIn('GET only', packet(2))
        self.assertEqual(len(specification(1)['cases']), 12)
        self.assertEqual(len(specification(2)['cases']), 21)
        self.assertEqual(len(workloads(1)), 4)
        self.assertEqual(len(workloads(2)), 8)
        self.assertEqual({w.clients for w in workloads(2)}, {256, 4096})

    def test_stage2_rejects_starter_and_snapshots_only_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'campaign'
            campaign.initialize(directory, '3')
            with self.assertRaisesRegex(ValueError, 'without starter'):
                controller.prepare(directory, 2, starter='unused.rs')
            run = Path(controller.prepare(directory, 2)['run'])
            self.assertTrue((run / 'builder-inputs/RULES.md').is_file())
            self.assertFalse((run / 'public-suite').exists())
            self.assertFalse((run / 'starter.rs').exists())
            self.assertEqual((run / 'launch-packet.md').read_text(), packet(2))

    def test_api_failure_forfeits_performance_without_invoking_load(self):
        for build_passed in (False, True):
            with self.subTest(build=build_passed), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'main.rs'
                source.write_text('fn main() {}')
                with patch('toksec.evaluate.sandbox.build', return_value={'passed': build_passed}), patch('toksec.evaluate.sandbox.evaluate', return_value={'passed': False, 'cases': [{'id': 'bad', 'passed': False}]}), patch('toksec.evaluate.sandbox.invoke_driver') as load:
                    result = evaluate(source, Path(tmp) / 'result', 2, performance=True)
                load.assert_not_called()
                self.assertEqual(result['grading']['performance_credit'], 0)
                self.assertEqual(result['grading']['performance_status'], 'failed_api')
