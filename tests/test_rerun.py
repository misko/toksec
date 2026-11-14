import tempfile
import unittest
from pathlib import Path
from toksec import campaign, controller, sandbox, reporting
from toksec.specification import ROOT


class RerunTests(unittest.TestCase):
    def test_fresh_budget_manual_submission_and_actual_server_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/'campaign'
            status=campaign.initialize(directory, '3')
            self.assertEqual(status['dollar_limit'], '3')
            self.assertEqual(status['used'],0)
            with self.assertRaisesRegex(ValueError, 'without starter'):
                controller.prepare(directory,1,7200,campaign.TERRA,ROOT/'starters/static.rs')
            run=Path(controller.prepare(directory,1,7200,campaign.TERRA)['run'])
            candidate=controller.submit(run,(ROOT/'starters/static.rs').read_text())['id']
            manifest=controller.read(run,'manifest.json')
            self.assertEqual(manifest['wall_seconds'],7200)
            self.assertEqual(controller.read(run)['best'],candidate)
            self.assertFalse(controller.read(run)['full_acceptance'])
            with sandbox.running(run/'candidates'/candidate,1) as runtime:
                pid=sandbox.server_pid(runtime['pid'],run/'candidates'/candidate)
                self.assertEqual(Path(f'/proc/{pid}/comm').read_text().strip(),'server')
                self.assertEqual(Path(f'/proc/{pid}/task/{pid}/children').read_text().strip(),'')
            self.assertIn('Passed checks',reporting.markdown(run))
