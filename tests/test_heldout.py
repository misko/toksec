import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toksec import campaign, controller, context, releases, sandbox
from toksec.specification import ROOT, packet


class HeldOutTests(unittest.TestCase):
    def test_builder_path_never_runs_full_suite(self):
        with tempfile.TemporaryDirectory() as tmp:
            campaign.initialize(Path(tmp)/'campaign', '3')
            run = Path(controller.prepare(Path(tmp)/'campaign', 1)['run'])
            source = (ROOT/'tests/fixtures/implementations/static.rs').read_text()
            with patch('toksec.sandbox.configuration_check', side_effect=AssertionError('held-out executed')):
                report = controller.submit(run, source)
                self.assertTrue(report['checks']['passed'])
                self.assertEqual([c['id'] for c in report['checks']['cases']], ['bootstrap'])
                controller.revalidate(run, 'latest')
                release = releases.initialize(run)
                checkpoint = context.checkpoint(run, packet(1))
            self.assertEqual(release['passed_checks'], ['bootstrap'])
            self.assertEqual(release['evaluation_scope'], 'visible_smoke_only')
            for text in (packet(1), json.dumps(checkpoint)):
                self.assertNotIn('absolute-header-deadline', text)
                self.assertNotIn('query-and-decoding', text)
            full = sandbox.evaluate(run/'candidates'/report['id'], 1)
            self.assertFalse(full['passed'])
            self.assertGreater(len(full['cases']), 1)

    def test_minimal_visible_cases(self):
        from stages.common.smoke import cases
        self.assertEqual([c.id for c in cases(1)], ['bootstrap'])
        self.assertEqual([c.id for c in cases(2)], ['bootstrap', 'smoke-head', 'smoke-persistent'])
        self.assertNotIn('pipeline-backpressure', packet(2))
        self.assertNotIn('connection-capacity', packet(2))

    def test_development_fixtures_do_not_expose_edge_case_inputs(self):
        from toksec.fixtures import create_smoke
        with tempfile.TemporaryDirectory() as tmp:
            create_smoke(tmp, 1)
            files = {str(p.relative_to(tmp)) for p in Path(tmp).rglob('*') if p.is_file()}
            self.assertEqual(files, {'server.conf', 'www/hello.txt', 'www/data/4096', 'www/data/65536'})
