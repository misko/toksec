import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stage10 import evaluation as stage10_evaluation
from toksec import evaluate
from toksec.artifacts import validate_evaluation
from toksec.evaluation_artifacts import write_evaluation

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('stage10_evaluate_cli', ROOT / 'evaluate.py')
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class Stage10EvaluationIntegrationTests(unittest.TestCase):
    def checks(self, passed=True):
        return {'passed': passed, 'cases': [{'id': 'https-get', 'passed': passed}],
                'unimplemented_requirements': ['transactional reload matrix']}

    def envelope(self, output, result):
        return write_evaluation(output, run_id='stage10-fixture',
                                release={'tag': 'release/000001', 'commit': 'a' * 40,
                                         'source_sha256': 'b' * 64},
                                contract_sha256='c' * 64, evaluator_sha256='d' * 64,
                                environment={}, coverage='partial', result=result)

    def test_shared_source_evaluator_dispatches_stage10(self):
        with patch.object(stage10_evaluation, 'evaluate_source', return_value={'coverage': 'partial'}) as adapter:
            result = evaluate.evaluate('main.cpp', 'output', 10, True, 'cpp')
        adapter.assert_called_once_with('main.cpp', 'output', True, 'cpp')
        self.assertEqual(result['coverage'], 'partial')

    def test_partial_api_success_runs_four_diagnostics_without_performance_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'main.cpp'; source.write_text('int main() {}')
            with patch.object(stage10_evaluation.sandbox, 'build', return_value={'passed': True}), \
                 patch.object(stage10_evaluation.evaluate, 'evaluate', return_value=self.checks()), \
                 patch.object(stage10_evaluation.benchmark, 'measure',
                              return_value={'eligible': True, 'failures': 0, 'requests_per_second': 100}) as measure:
                result = evaluate.evaluate(source, root / 'output', 10, True, 'cpp')
            self.assertEqual(measure.call_count, 4)
            self.assertEqual({(c.args[2], c.args[3]) for c in measure.call_args_list},
                             {(256, False), (4096, False), (256, True), (4096, True)})
            self.assertFalse(result['final_grade_eligible'])
            self.assertFalse(result['grading']['full_api_passed'])
            self.assertEqual(result['grading']['performance_credit'], 0)
            self.assertTrue(all(not item['eligible'] and item['provisional']
                                for item in result['benchmarks'].values()))
            record = self.envelope(root / 'output', result)
            self.assertEqual(record['status'], 'partial')
            self.assertEqual(record['performance']['status'], 'provisional')
            self.assertEqual(record['performance']['credit'], 0)
            self.assertEqual(evaluate.exit_code(result, True), 4)
            self.assertIn('uncalibrated diagnostics', (root / 'output/report.md').read_text())
            self.assertEqual(json.loads((root / 'output/api.json').read_text())['unimplemented_requirements'],
                             ['transactional reload matrix'])

    def test_failed_partial_api_never_runs_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'main.cpp'; source.write_text('int main() {}')
            with patch.object(stage10_evaluation.sandbox, 'build', return_value={'passed': True}), \
                 patch.object(stage10_evaluation.evaluate, 'evaluate', return_value=self.checks(False)), \
                 patch.object(stage10_evaluation.benchmark, 'measure') as measure:
                result = evaluate.evaluate(source, root / 'output', 10, True, 'cpp')
            measure.assert_not_called()
            self.assertEqual(evaluate.exit_code(result, True), 2)
            record = self.envelope(root / 'output', result)
            self.assertEqual(record['performance'], {'status': 'skipped_api_failure', 'credit': 0, 'metrics': None})

    def test_diagnostic_driver_failure_is_reported_as_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'main.cpp'; source.write_text('int main() {}')
            with patch.object(stage10_evaluation.sandbox, 'build', return_value={'passed': True}), \
                 patch.object(stage10_evaluation.evaluate, 'evaluate', return_value=self.checks()), \
                 patch.object(stage10_evaluation.benchmark, 'measure', side_effect=RuntimeError('driver failed')):
                result = evaluate.evaluate(source, root / 'output', 10, True, 'cpp')
            self.assertEqual(len(result['diagnostic_errors']), 4)
            self.assertEqual(evaluate.exit_code(result, True), 1)
            self.assertFalse(result['final_grade_eligible'])

    def test_source_cli_accepts_stage10_and_returns_partial_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = {'checks': self.checks(), 'coverage': 'partial', 'final_grade_eligible': False}
            with patch.object(CLI.evaluate, 'evaluate', return_value=result) as adapter, \
                 contextlib.redirect_stdout(io.StringIO()):
                code = CLI.main(['--section', 'api', '--level', '10', '--language', 'cpp',
                                 '--source', 'main.cpp', '--output', temporary])
            self.assertEqual(code, 4)
            self.assertEqual(adapter.call_args.args[2], 10)

    def test_tagged_stage10_cli_does_not_require_legacy_campaign_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = {'checks': self.checks(), 'coverage': 'partial', 'final_grade_eligible': False}
            (Path(temporary) / 'manifest.json').write_text(json.dumps({'stage': 10}))
            with patch.object(CLI.releases, 'grade', return_value=result) as grade, \
                 contextlib.redirect_stdout(io.StringIO()):
                code = CLI.main(['--section', 'performance', '--run', temporary, '--output', temporary])
            self.assertEqual(code, 4)
            grade.assert_called_once_with(Path(temporary), Path(temporary), True)
            self.assertTrue((Path(temporary) / 'run.lock').exists())

    def test_schema_prevents_provisional_metrics_becoming_a_full_grade(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = {'checks': self.checks(), 'performance_scope': 'provisional_diagnostics_only',
                      'benchmarks': {'http': {'eligible': False, 'failures': 0}}}
            record = self.envelope(temporary, result)
            for changes in ({'status': 'passed'}, {'coverage': 'full'},
                            {'performance': dict(record['performance'], credit=None)}):
                invalid = copy.deepcopy(record); invalid.update(changes)
                with self.assertRaises(ValueError):
                    validate_evaluation(invalid)

    @unittest.skipUnless(os.environ.get('TOKSEC_STAGE10_SANDBOX_TEST') == '1', 'explicit live sandbox opt-in')
    def test_real_stage10_build_and_failed_server_checks_through_shared_evaluator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'main.cpp'; source.write_text('int main() { return 0; }')
            result = evaluate.evaluate(source, root / 'output', 10, True, 'cpp')
            self.assertTrue(result['build']['passed'])
            self.assertFalse(result['checks']['passed'])
            self.assertNotIn('benchmarks', result)
            self.assertEqual(evaluate.exit_code(result, True), 2)
