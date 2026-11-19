import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path
from toksec.storage import atomic_json
from toksec import campaign, controller, releases
from toksec.specification import ROOT

spec = importlib.util.spec_from_file_location('release_analysis', ROOT/'scripts/analyze_releases.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class ReleaseAnalysisTests(unittest.TestCase):
    def test_export_and_rebuild_tagged_source_after_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign.initialize(root/'campaign', '3')
            run = Path(controller.prepare(root/'campaign', 1)['run'])
            controller.submit(run, (ROOT/'tests/fixtures/implementations/static.rs').read_text())
            manifest = controller.read(run, 'manifest.json')
            manifest['started_unix'] = time.time()
            atomic_json(run/'manifest.json', manifest)
            release = releases.initialize(run)
            with self.assertRaises(ValueError):
                analysis.analyze(run, root/'analysis')
            state = controller.read(run)
            state.update(finished=True, ended_unix=time.time())
            atomic_json(run/'state.json', state)
            (run/'repository/main.rs').write_text('broken untagged source')
            timeline = analysis.analyze(run, root/'analysis')
            self.assertTrue((root/'analysis/implementation/.git').is_dir())
            self.assertEqual((root/'analysis/implementation/main.rs').read_text(), (ROOT/'tests/fixtures/implementations/static.rs').read_text())
            self.assertEqual(timeline['releases'][0]['commit'], release['commit'])
            self.assertTrue(timeline['releases'][0]['build_passed'])
            self.assertEqual(release['passed_checks'], ['bootstrap'])
            self.assertGreater(timeline['releases'][0]['passed'], len(release['passed_checks']))
            self.assertEqual(timeline['releases'][0]['benchmarks'], {})
            self.assertEqual(analysis.analyze(run, root/'analysis'), timeline)
