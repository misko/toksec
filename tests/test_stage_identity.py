import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from toksec import provenance
from toksec.stages import identifier, number, title
from toksec.specification import packet, publish


class StageIdentityTests(unittest.TestCase):
    def test_canonical_format_and_historical_reader(self):
        for n, expected in ((1, 'stage-01'), (10, 'stage-10'), (100, 'stage-100')):
            self.assertEqual(identifier(n), expected)
            self.assertEqual(title(n), f'Stage {n}')
            self.assertEqual(number({'level': n}), n)
            self.assertEqual(number({'stage': n, 'level': n}), n)
        for value in (0, -1, True, '01', {'stage': 1, 'level': 2}, {'stage': 1, 'level': True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_current_inputs_have_no_protocol_version_labels(self):
        for language in ('rust', 'cpp'):
            with tempfile.TemporaryDirectory() as temp:
                for stage in (1, 2, 3, 4, 5, 10):
                    publish(temp, language, stage)
                    self.assertTrue((Path(temp) / f'{identifier(stage)}.md').is_file())
                    spec = json.loads((Path(temp) / f'{identifier(stage)}.json').read_text())
                    self.assertEqual(spec['stage'], stage)
                    self.assertNotIn('version', spec)
                    self.assertNotIn('level', spec)
                    self.assertNotIn('http-v8', packet(stage, language))
                    self.assertNotIn('tasks/v8', packet(stage, language))

    def test_checkout_tracks_commits_and_refuses_dirty_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      text=True, capture_output=True).stdout.strip()
            git('init')
            source = root / 'source.py'; source.write_text('original')
            git('add', 'source.py')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
            commit = git('rev-parse', 'HEAD')
            self.assertEqual(provenance.checkout(True, root), {'toksec_commit': commit, 'toksec_dirty': False})
            source.write_text('modified')
            self.assertEqual(provenance.checkout(root=root)['toksec_commit'], commit)
            self.assertTrue(provenance.checkout(root=root)['toksec_dirty'])
            with self.assertRaisesRegex(ValueError, 'dirty'):
                provenance.checkout(True, root)
            git('checkout', '--', 'source.py')
            (root / 'untracked.py').write_text('new')
            with self.assertRaisesRegex(ValueError, 'dirty'):
                provenance.checkout(True, root)

    def test_run_name_is_canonical_and_collision_resistant(self):
        first = provenance.run_name(1, 'cpp', 'a' * 40)
        self.assertRegex(first, r'^stage-01__cpp__\d{8}T\d{6}Z__a{12}__[a-f0-9]{8}$')
        self.assertNotEqual(first, provenance.run_name(1, 'cpp', 'a' * 40))

    def test_new_evaluation_keeps_evaluator_and_run_commits_distinct(self):
        from toksec.evaluation_artifacts import write_evaluation
        with tempfile.TemporaryDirectory() as temp:
            result = {'toksec_commit': 'a' * 40, 'toksec_dirty': False,
                      'run_toksec_commit': 'b' * 40,
                      'build': {'passed': False}, 'checks': {'passed': False, 'cases': []}}
            record = write_evaluation(temp, run_id='run',
                                     release={'tag': 'release/000001', 'commit': 'c' * 40, 'source_sha256': 'd' * 64},
                                     contract_sha256='e' * 64, evaluator_sha256='f' * 64,
                                     environment={}, coverage='partial', result=result)
            self.assertEqual(record['toksec_commit'], 'a' * 40)
            self.assertEqual(record['run_toksec_commit'], 'b' * 40)
            self.assertEqual(record['release']['commit'], 'c' * 40)

    def test_new_preparation_refuses_dirty_framework_before_creating_run(self):
        from toksec import controller as runner
        with tempfile.TemporaryDirectory() as temp, patch.object(runner, 'checkout', side_effect=ValueError('dirty')):
            run = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'dirty'):
                runner.counted_prepare(run)
            self.assertFalse(run.exists())

    def test_both_runners_record_preparation_commit(self):
        from toksec import campaign, controller
        for stage in (1, 10):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'campaign'
                campaign.initialize(root, '3')
                run = Path(controller.prepare(root, stage, language='cpp')['run'])
                manifest = json.loads((run / 'manifest.json').read_text())
                self.assertEqual(manifest['toksec_commit'], provenance.checkout()['toksec_commit'])
                self.assertFalse(manifest['toksec_dirty'])
                self.assertEqual(manifest['stage'], stage)
                self.assertNotIn('level', manifest)
                self.assertTrue(run.name.startswith(f'{identifier(stage)}__cpp__'))
                self.assertIn(manifest['toksec_commit'][:12], run.name)

    def test_source_evaluators_capture_commit_even_on_build_failure(self):
        from toksec import evaluate
        from toksec.sandbox import cgroup as tls
        for stage, target in ((1, evaluate.sandbox), (10, tls)):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); source = root / 'main.cpp'; source.write_text('broken code')
                with patch.object(target, 'build', return_value={'passed': False}):
                    result = evaluate.evaluate(source, root / 'evaluation', stage, language='cpp')
                self.assertEqual(result['toksec_commit'], provenance.checkout()['toksec_commit'])
                self.assertEqual(result['toksec_dirty'], provenance.checkout()['toksec_dirty'])
                self.assertEqual(result['stage'], stage)
