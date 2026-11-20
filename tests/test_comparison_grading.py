import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.analyze_releases import analyze
from toksec import controller, releases
from toksec.artifacts import write_artifact
from toksec.result_storage import files, publish_run
from toksec.specification import specification
from toksec.storage import atomic_json


class ComparisonGradingTests(unittest.TestCase):
    def make_run(self, root):
        run = root / 'raw'
        run.mkdir()
        framework = 'c' * 64
        write_artifact(run, 14, 'cpp')
        contract = hashlib.sha256((run / 'artifact.json').read_bytes()).hexdigest()
        atomic_json(run / 'manifest.json', {
            'stage': 14, 'language': 'cpp', 'wall_seconds': 7200, 'campaign': str(root),
            'started_unix': 1, 'fingerprint': framework, 'artifact_sha256': contract,
            'builder_evaluation_scope': 'visible_smoke_only',
        })
        atomic_json(run / 'state.json', {'finished': True, 'ended_unix': 10})
        atomic_json(run / 'specification.json', specification(14, 'cpp'))
        atomic_json(root / 'ledger.json', {'dollar_limit': '3'})
        (run / 'launch-packet.md').write_text('Frozen instructions')
        releases.git(run, 'init', '--initial-branch=main')
        for n in (1, 2):
            source = f'invalid tagged source {n}'
            release = {'tag': f'release/{n:06}', 'framework': framework, 'stage': 14, 'language': 'cpp',
                       'candidate': f'candidate-{n}', 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                       'artifact_sha256': contract, 'recorded_unix': n + 1,
                       'capacity': {'spent_usd_upper_bound': str(n / 10)}}
            (run / 'repository/main.cpp').write_text(source)
            atomic_json(run / 'repository/release.json', release)
            releases.git(run, 'add', 'main.cpp', 'release.json')
            releases.git(run, 'commit', '-m', 'milestone')
            releases.git(run, 'tag', release['tag'])
        (run / 'repository/main.cpp').write_text('changed after release')
        return run

    def test_archived_tags_are_bound_to_new_grades_and_keep_tip_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root)
            analysis = root / 'series'
            frozen = files(run / 'builder-inputs')
            with self.assertRaisesRegex(ValueError, 'different evaluator'):
                analyze(run, analysis)
            with patch('toksec.evaluate.sandbox.invoke_driver') as load:
                timeline = analyze(run, analysis, comparison=True, performance=False)
                load.assert_not_called()
            self.assertEqual(analyze(run, analysis, comparison=True, performance=False), timeline)
            self.assertEqual([row['elapsed_seconds'] for row in timeline['releases']], [1, 2])
            self.assertEqual([row['spent_usd_upper_bound'] for row in timeline['releases']], ['0.1', '0.2'])
            first, last = timeline['releases']
            target = root / 'published'
            publish_run(run, target)
            sealed = files(target / 'raw/implementation')
            # A later regrade of the older release must leave the final-tag report discoverable.
            # Only the publication will now carry the last tag's previous grade.
            shutil.move(str(run / 'evaluation' / last['evaluation_id']), str(root / 'preserved-grade'))
            older = run / 'evaluation/regraded-first'
            result = releases.grade(run, older, tag=first['tag'], comparison=True)
            self.assertEqual(result['source_sha256'], first['source_sha256'])
            record = publish_run(run, target)
            self.assertEqual(record['paths']['latest_evaluation'], 'evaluation/' + last['evaluation_id'])
            self.assertEqual(files(target / 'raw/implementation'), sealed)
            for row in (first, last):
                envelope = json.loads((target / 'raw/evaluation' / row['evaluation_id'] / 'evaluation.json').read_text())
                self.assertEqual(envelope['release']['commit'], row['commit'])
                self.assertEqual(envelope['release']['source_sha256'], row['source_sha256'])
                self.assertEqual(envelope['environment']['cpu_affinity'], sorted(os.sched_getaffinity(0)))
                self.assertNotEqual(envelope['evaluator_sha256'], envelope['environment']['builder_framework'])
                self.assertEqual(envelope['performance']['status'], 'skipped_api_failure')
            self.assertEqual(files(run / 'builder-inputs'), frozen)
            with self.assertRaisesRegex(ValueError, 'another source, evaluator, host or measurement policy'):
                analyze(run, analysis, comparison=True, performance=True)

    def test_no_tag_series_records_terminal_cost_and_time_without_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root)
            shutil.rmtree(run / 'repository')
            capacity = {'spent_usd_upper_bound': '0.01382725', 'reserved_usd': '0.200'}
            atomic_json(run / 'result.json', {'capacity': capacity})
            with patch.object(releases, 'grade') as grade:
                timeline = analyze(run, root / 'series', comparison=True)
                grade.assert_not_called()
            self.assertEqual(timeline['releases'], [])
            self.assertEqual(timeline['ended_unix'] - timeline['started_unix'], 9)
            self.assertEqual(timeline['terminal_capacity'], capacity)
            self.assertFalse((run / 'evaluation').exists())
            self.assertFalse((root / 'series/implementation.bundle').exists())
            self.assertEqual(timeline, controller.read(root / 'series', 'timeline.json'))

    def test_gateway_calibration_matches_host_code_and_selected_cells(self):
        from toksec import gateway_calibration
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root)
            manifest = controller.read(run, 'manifest.json')
            cell = specification(14, 'cpp')['benchmarks'][0]
            calibration = {'calibration_id': 'stage14-control', 'stage': 14, 'status': 'completed',
                           'environment': gateway_calibration.environment(),
                           'measurement_fingerprint': gateway_calibration.measurement_fingerprint(14),
                           'workloads': {cell['id']: cell},
                           'cells': {cell['id']: {'qualified': False, 'reasons': ['generator_saturated']}}}
            receipt = root / 'calibration.json'
            atomic_json(receipt, calibration)
            metadata = releases.grade_environment(run, manifest, comparison=True, calibration=receipt)
            self.assertEqual(metadata['calibration']['cells'], calibration['cells'])
            self.assertEqual(metadata['calibration']['sha256'], hashlib.sha256(receipt.read_bytes()).hexdigest())
            calibration['environment']['cpu_affinity'] = []
            atomic_json(receipt, calibration)
            with self.assertRaisesRegex(ValueError, 'calibration does not match'):
                releases.grade_environment(run, manifest, comparison=True, calibration=receipt)

    def test_missing_gateway_calibration_retains_rounds_as_unqualified_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root)
            sample = {'eligible': True, 'failures': 0, 'median_rps': 100, 'rounds': [{'p99_ms': 1.2}]}
            result = {'stage': 14, 'build': {'passed': True}, 'checks': {
                'passed': True, 'cases': [{'id': 'fixture-api', 'passed': True}]},
                'benchmarks': {'fixture-load': sample}, 'grading': {}}
            def measured(_source, output, *_args, **_kwargs):
                output.mkdir(parents=True)
                return result
            with patch.object(releases.evaluate, 'evaluate', side_effect=measured):
                destination = run / 'evaluation' / 'diagnostic'
                releases.grade(run, destination, performance=True, comparison=True)
            performance = controller.read(destination, 'performance.json')
            self.assertEqual(performance['status'], 'invalid_measurement')
            self.assertEqual(performance['credit'], 0)
            self.assertIs(performance['metrics']['fixture-load']['calibration_qualified'], False)
            self.assertEqual(performance['metrics']['fixture-load']['rounds'], [{'p99_ms': 1.2}])

    def test_rejects_changed_contract_and_unknown_tags_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.make_run(root)
            with patch('toksec.evaluate.sandbox.build') as build:
                with self.assertRaisesRegex(ValueError, 'no completed release'):
                    releases.grade(run, comparison=True, tag='release/999999')
                frozen = controller.read(run, 'specification.json')
                frozen['benchmarks'][0]['clients'] -= 1
                atomic_json(run / 'specification.json', frozen)
                with self.assertRaisesRegex(ValueError, 'stage specification changed'):
                    releases.grade(run, comparison=True)
                build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
