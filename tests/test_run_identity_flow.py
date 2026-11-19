"""A run retains its identity through relocation, grading, and publication."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from toksec import campaign, controller, releases
from toksec.result_storage import publish_run
from toksec.storage import atomic_json


class RunIdentityFlowTests(unittest.TestCase):
    def test_both_stage_paths_publish_the_persisted_id_and_parent_report(self):
        for stage in (1, 10):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                campaign.initialize(root / 'campaign', '3')
                run = Path(controller.prepare(root / 'campaign', stage, language='cpp')['run'])
                manifest = controller.read(run, 'manifest.json')
                identity = manifest['run_id']
                self.assertEqual(identity, run.name)
                manifest['started_unix'] = 1
                atomic_json(run / 'manifest.json', manifest)
                repository = run / 'repository'
                repository.mkdir()
                source = 'int main( { invalid source; }\n'
                (repository / 'main.cpp').write_text(source)
                tag = {'tag': 'release/000001', 'stage': stage, 'language': 'cpp',
                       'candidate': 'fixture', 'framework': manifest.get('framework', manifest.get('fingerprint')),
                       'source_sha256': hashlib.sha256(source.encode()).hexdigest()}
                atomic_json(repository / 'release.json', tag)
                def git(*arguments):
                    subprocess.run(['git', '-C', str(repository), '-c', 'core.hooksPath=/dev/null',
                                    '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                                    '-c', 'commit.gpgsign=false', *arguments], check=True, capture_output=True)
                git('init', '--initial-branch=main')
                git('add', 'main.cpp', 'release.json')
                git('commit', '-m', 'Failed submission fixture')
                git('tag', tag['tag'])
                state = controller.read(run)
                state.update(finished=True, tags=[tag])
                atomic_json(run / 'state.json', state)
                # Renaming an operational directory must not rename the experiment.
                moved = run.with_name('relocated-raw-directory')
                run.rename(moved)
                output = moved / 'evaluation' / 'parent-check'
                report = releases.grade(moved, output, performance=True)
                self.assertFalse(report['build']['passed'])
                envelope = json.loads((output / 'evaluation.json').read_text())
                self.assertEqual(envelope['run_id'], identity)
                self.assertEqual(envelope['performance']['credit'], 0)
                record = publish_run(moved, root / 'results')
                published = root / 'results' / identity
                self.assertTrue(published.is_dir())
                self.assertEqual(record['id'], identity)
                self.assertEqual(record['run_id'], identity)
                self.assertEqual(record['path'], identity)
                self.assertEqual((published / 'evaluation/parent-check/evaluation.json').read_bytes(),
                                 (output / 'evaluation.json').read_bytes())
                index = json.loads((root / 'results/index.json').read_text())
                self.assertEqual(index['runs'][0]['run_id'], identity)
                if stage == 10:
                    self.assertEqual(envelope['coverage'], 'partial')
                    self.assertEqual(record['performance_scope'], 'provisional')
