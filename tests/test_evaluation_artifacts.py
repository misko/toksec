import json
from pathlib import Path
import tempfile
import unittest

from toksec.evaluation_artifacts import write_evaluation


class EvaluationArtifactTests(unittest.TestCase):
    def args(self):
        return dict(run_id='example', release={'tag': 'release/000001',
                    'commit': 'a' * 40, 'source_sha256': 'b' * 64},
                    contract_sha256='c' * 64, evaluator_sha256='d' * 64,
                    environment={'platform': 'test'}, coverage='full',
                    result={'checks': {'passed': True, 'cases': [{'id': 'api', 'passed': True}]}})

    def test_api_failure_blocks_supplied_performance(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args()
            args['result']['checks'] = {'passed': False, 'cases': [{'id': 'api', 'passed': False}]}
            args['performance'] = {'load': {'eligible': True, 'failures': 0, 'rps': 100}}
            record = write_evaluation(tmp, **args)
            self.assertEqual(record['performance'], {'status': 'skipped_api_failure', 'credit': 0, 'metrics': None})
            self.assertEqual(record['status'], 'failed')

    def test_build_failure_has_no_behavioral_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(); args['result'] = {'build': {'passed': False}}
            record = write_evaluation(tmp, **args)
            self.assertEqual(record['api'], {'status': 'failed', 'passed': 0, 'total': 0})
            self.assertEqual(record['performance']['status'], 'skipped_api_failure')

    def test_partial_coverage_never_claims_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(); args['coverage'] = 'partial'
            record = write_evaluation(tmp, **args)
            self.assertEqual(record['status'], 'partial')
            self.assertEqual(record['performance']['status'], 'skipped_incomplete_suite')

    def test_evaluation_is_bound_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args()
            record = write_evaluation(tmp, **args)
            self.assertEqual(write_evaluation(tmp, **args), record)
            args['release']['commit'] = 'e' * 40
            with self.assertRaisesRegex(ValueError, 'new evaluation ID'):
                write_evaluation(tmp, **args)
            self.assertEqual(json.loads((Path(tmp) / 'evaluation.json').read_text()), record)

    def test_missing_history_and_unrun_evaluation_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(); args.update(release={}, contract_sha256=None,
                                            evaluator_sha256=None, coverage='unknown', result=None)
            record = write_evaluation(tmp, **args)
            self.assertEqual(record['provenance_status'], 'historical_incomplete')
            self.assertEqual(record['status'], 'not_run')
            self.assertIsNone(record['api']['total'])
            self.assertEqual(record['performance']['status'], 'not_run')

    def test_saturated_generator_measurement_is_retained_without_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(); args['performance'] = {'load': {'eligible': False, 'failures': 0, 'rps': 100}}
            record = write_evaluation(tmp, **args)
            self.assertEqual(record['performance']['status'], 'invalid_measurement')
            self.assertEqual(record['performance']['credit'], 0)
            self.assertEqual(record['performance']['metrics'], args['performance'])

    def test_infrastructure_summary_is_not_an_extra_behavioral_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(); args['coverage'] = 'partial'
            args['result'] = {'passed': False, 'cases': [{'id': 'api', 'passed': False},
                                                       {'id': 'api-runtime', 'passed': False}]}
            self.assertEqual(write_evaluation(tmp, **args)['api']['total'], 1)

    def test_symlink_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); destination = root / 'evaluation'; destination.mkdir()
            outside = root / 'outside'; outside.write_text('unchanged')
            (destination / 'report.md').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                write_evaluation(destination, **self.args())
            self.assertEqual(outside.read_text(), 'unchanged')
