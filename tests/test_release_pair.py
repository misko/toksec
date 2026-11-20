import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from scripts.compare_release_pair import compare_tags


class ReleasePairTests(unittest.TestCase):
    def test_final_failed_tag_prevents_selection_of_earlier_successes(self):
        self.assertEqual(self.measure(['passed', 'passed', 'failed'])['status'], 'unavailable')

    def test_one_passing_tag_cannot_measure_a_gain(self):
        result = self.measure(['failed', 'passed'])
        self.assertEqual(result['reason'], 'one distinct API-clean endpoint')

    def test_comparison_checks_calibration_before_building(self):
        with patch('scripts.compare_release_pair.sandbox.build') as build:
            result = self.measure(['passed', 'passed'])
        build.assert_not_called()
        self.assertEqual(result['reason'], 'confirmation cell did not qualify')

    def measure(self, statuses):
        rows = [{'tag': f'release/{i:06d}', 'commit': str(i), 'source_sha256': str(i),
                 'evaluation_id': uuid.uuid4().hex} for i in range(1, 1 + len(statuses))]
        calibration = {'id': 'test-calibration'}
        env = {'evaluator_framework': 'current', 'calibration': calibration}
        envelopes = [{'run_id': 'run', 'release': {k: row[k] for k in ('tag', 'commit', 'source_sha256')},
                      'contract_sha256': 'contract', 'evaluator_sha256': 'current', 'environment': env,
                      'coverage': 'full', 'api': {'status': status}} for status, row in zip(statuses, rows)]
        parent = {'run_id': 'run', 'stage': 14, 'framework': 'current', 'releases': rows,
                  'calibration': calibration}
        manifest = {'stage': 14, 'artifact_sha256': 'contract', 'language': 'cpp'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration_file = root / 'calibration.json'
            calibration_file.write_text('{"cells":{"gateway-14-admitted-4096-4096":{"qualified":false,"reasons":["noise"]}}}')
            with (patch('scripts.compare_release_pair.controller.read', side_effect=[manifest, *envelopes]),
                  patch('scripts.compare_release_pair.run_identity', return_value='run'),
                  patch('scripts.compare_release_pair.releases.grade_environment', return_value=env),
                  patch('scripts.compare_release_pair.releases.list_releases', return_value=rows),
                  patch('scripts.compare_release_pair.validate_evaluation', side_effect=lambda e: e)):
                return compare_tags(root, parent, calibration_file, 'gateway-14-admitted-4096-4096')
