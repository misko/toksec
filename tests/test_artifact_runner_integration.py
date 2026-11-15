import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec.storage import atomic_json
from toksec import campaign, controller, releases
from toksec.artifacts import read_artifact
from toksec.specification import packet
from toksec.sandbox import cgroup
from toksec.stages import module as stage_module
stage10_api = stage_module(10, 'api')


class ArtifactRunnerIntegrationTests(unittest.TestCase):
    def prepare_legacy(self, directory):
        campaign.initialize(directory, '3')
        with patch('toksec.controller.subprocess.check_output', return_value='compiler fixture'):
            return Path(controller.prepare(directory, 2, language='cpp')['run'])

    def prepare_stage10(self, directory):
        with patch('toksec.controller.subprocess.check_output', return_value='compiler fixture'):
            controller.counted_prepare(directory)
        return directory

    def test_both_prepares_supply_frozen_contract_and_shared_instructions(self):
        for kind in ('legacy', 'stage10'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'campaign'
                run = self.prepare_legacy(destination) if kind == 'legacy' else self.prepare_stage10(destination)
                manifest = json.loads((run / 'manifest.json').read_text())
                stage = 2 if kind == 'legacy' else 10
                contract = read_artifact(run, stage, 'cpp', manifest['artifact_sha256'])
                self.assertEqual(contract['submission']['source_file'], 'main.cpp')
                self.assertEqual((run / 'artifact.json').read_bytes(), (run / 'builder-inputs/artifact.json').read_bytes())
                self.assertEqual(manifest['input_sha256']['artifact.json'], manifest['artifact_sha256'])
                prompt = (run / 'launch-packet.md').read_text()
                self.assertIn('# Artifact ownership and submission format', prompt)
                self.assertIn(json.dumps(contract, indent=2, sort_keys=True), prompt)
                self.assertNotIn(str(run), prompt)
                self.assertFalse((run / 'builder-inputs/evaluation').exists())
                for supplied in (run / 'builder-inputs').rglob('*'):
                    self.assertNotIn('grading', supplied.relative_to(run / 'builder-inputs').parts)
                if kind == 'legacy':
                    self.assertEqual(prompt, packet(2, 'cpp'))

    def test_both_runners_reject_tampered_contract_before_compilation(self):
        for kind in ('legacy', 'stage10'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'campaign'
                run = self.prepare_legacy(destination) if kind == 'legacy' else self.prepare_stage10(destination)
                (run / 'artifact.json').write_text('{}')
                target = 'toksec.controller.sandbox.build' if kind == 'legacy' else 'toksec.sandbox.cgroup.build'
                submit = controller.submit if kind == 'legacy' else controller.counted_submit
                with patch(target) as build, self.assertRaisesRegex(ValueError, 'contract hash mismatch'):
                    submit(run, 'int main() {}')
                build.assert_not_called()

    def test_both_runners_reject_invalid_source_before_compilation(self):
        for kind in ('legacy', 'stage10'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'campaign'
                run = self.prepare_legacy(destination) if kind == 'legacy' else self.prepare_stage10(destination)
                target = 'toksec.controller.sandbox.build' if kind == 'legacy' else 'toksec.sandbox.cgroup.build'
                submit = controller.submit if kind == 'legacy' else controller.counted_submit
                with patch(target) as build:
                    for source in ('x' * 1048577, '\ud800', {'source': 'wrong tool shape'}):
                        with self.assertRaises(ValueError):
                            submit(run, source)
                    build.assert_not_called()

    def test_stage10_grade_extracts_tag_into_parent_evaluation_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self.prepare_stage10(Path(temporary) / 'run')
            source = 'int main() {}\n'
            digest = hashlib.sha256(source.encode()).hexdigest()
            state = controller.read(run)
            state['tags'] = [{'tag': 'release/000001', 'source_sha256': digest}]
            atomic_json(run / 'state.json', state)
            def git(_run, *args):
                return source if args[0] == 'show' else 'a' * 40
            with patch.object(releases, 'git', side_effect=git), \
                 patch.object(cgroup, 'build', return_value={'passed': False}), \
                 patch.object(stage10_api, 'evaluate') as evaluate, \
                 patch('toksec.evaluation_artifacts.write_evaluation') as write:
                result = releases.counted_grade(run)
            evaluate.assert_not_called()
            self.assertFalse(result['build']['passed'])
            args, kwargs = write.call_args
            self.assertEqual(args[0].parent, run / 'evaluation')
            self.assertEqual(kwargs['coverage'], 'partial')
            self.assertEqual(kwargs['release']['commit'], 'a' * 40)
            self.assertEqual(kwargs['release']['source_sha256'], digest)
            self.assertFalse((run / 'repository/evaluation.json').exists())

    def test_shared_grade_writes_parent_envelope_for_pinned_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self.prepare_legacy(Path(temporary) / 'campaign')
            manifest = controller.read(run, 'manifest.json')
            source = 'int main() {}\n'
            release = {'tag': 'release/000001', 'commit': 'b' * 40,
                       'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                       'level': 2, 'language': 'cpp', 'framework': manifest['fingerprint']}
            def evaluate(source_path, output, *args, **kwargs):
                output.mkdir(parents=True)
                self.assertEqual(source_path.name, 'main.cpp')
                self.assertEqual(source_path.read_text(), source)
                return {'build': {'passed': False}}
            with patch.object(releases, 'list_releases', return_value=[release]), \
                 patch.object(releases, 'git', return_value=source), \
                 patch.object(releases.evaluate, 'evaluate', side_effect=evaluate), \
                 patch('toksec.evaluation_artifacts.write_evaluation') as write:
                result = releases.grade(run)
            args, kwargs = write.call_args
            self.assertEqual(args[0].parent, run / 'evaluation')
            self.assertEqual(kwargs['coverage'], 'full')
            self.assertEqual(kwargs['contract_sha256'], manifest['artifact_sha256'])
            self.assertEqual(result['release']['commit'], 'b' * 40)
            self.assertFalse((run / 'repository/evaluation.json').exists())

    def test_shared_grade_rejects_reports_inside_implementation(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / 'run'
            with patch.object(releases, 'list_releases') as listing:
                with self.assertRaisesRegex(ValueError, 'inside the implementation'):
                    releases.grade(run, run / 'repository/reports')
                listing.assert_not_called()

    def test_stage10_grade_rejects_reports_inside_implementation(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / 'run'
            with patch.object(releases, 'git') as git:
                with self.assertRaisesRegex(ValueError, 'inside the implementation'):
                    releases.counted_grade(run, run / 'repository/reports')
                git.assert_not_called()
