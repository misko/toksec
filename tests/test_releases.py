import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toksec import campaign, controller, releases
from toksec.specification import ROOT


class ReleaseTests(unittest.TestCase):
    def test_interruption_and_dirty_worktree_grade_last_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            campaign_dir=Path(tmp)/'campaign'
            campaign.initialize(campaign_dir,'3')
            run=Path(controller.prepare(campaign_dir,1)['run'])
            controller.submit(run, (ROOT/'starters/static.rs').read_text())
            first=releases.initialize(run)
            self.assertEqual(first['tag'],'release/000001')
            self.assertEqual(releases.initialize(run)['commit'],first['commit'])
            source=(ROOT/'starters/static.rs').read_text()+'\n'
            controller.submit(run,source)
            original=releases.git
            def interrupted(run,*args):
                if args[0]=='tag' and '--list' not in args:
                    raise RuntimeError('interrupted before publishing tag')
                return original(run,*args)
            with patch('toksec.releases.git',side_effect=interrupted):
                with self.assertRaises(RuntimeError):
                    releases.publish(run,'Working change')
            self.assertEqual(releases.list_releases(run)[-1]['commit'],first['commit'])
            second=releases.publish(run,'Working change')
            self.assertEqual(second['tag'],'release/000002')
            (run/'repository'/'main.rs').write_text('broken untagged code')
            grade=releases.grade(run,Path(tmp)/'grade')
            self.assertTrue(grade['build']['passed'])
            self.assertEqual(grade['release']['commit'],second['commit'])
            self.assertEqual((Path(tmp)/'grade/candidate/main.rs').read_text(),source)
            controller.submit(run,'fn main() { broken }')
            with self.assertRaises(ValueError):releases.publish(run,'Broken release')
            self.assertEqual(releases.list_releases(run)[-1]['tag'],'release/000002')
