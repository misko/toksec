"""Public commands select Stage 10 without bypassing its budget or grade labels."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec import __main__ as cli, campaign, controller, runner
from stage10 import runner as tls_runner
from toksec.stage_dispatch import stage_of


class UnifiedStage10CliTests(unittest.TestCase):
    def command(self, *arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(list(map(str, arguments)))
        return code, json.loads(stream.getvalue())

    def test_regular_prepare_uses_shared_policy_and_unspent_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'campaign'
            self.assertEqual(self.command('init', '--campaign', root, '--budget-usd', '2')[0], 0)
            code, result = self.command('prepare', '--campaign', root, '--level', '10', '--language', 'cpp')
            self.assertEqual(code, 0, result)
            run = Path(result['run'])
            manifest = json.loads((run / 'manifest.json').read_text())
            self.assertEqual(stage_of(run), 10)
            self.assertEqual(manifest['model'], 'gpt-6.1-terra')
            self.assertEqual(manifest['campaign'], str(root.resolve()))
            self.assertEqual(manifest['api_coverage'], 'partial')
            self.assertEqual(manifest['performance_scope'], 'provisional')
            self.assertEqual(campaign.read(root)['requests'], [])
            self.assertFalse((run / 'repository' / 'main.cpp').exists())
            code, status = self.command('status', '--campaign', root)
            self.assertEqual(code, 0)
            self.assertIn('stage10', status)
            # Both public entry points must route through parent accounting.
            with patch('toksec.stage10_campaign.run_loop', return_value={'finished': True}) as invoke:
                runner.run_loop(run, object())
                tls_runner.run_loop(run, object())
            self.assertEqual(invoke.call_count, 2)

    def test_check_and_grade_do_not_promote_partial_success(self):
        partial = {'coverage': 'partial', 'final_grade_eligible': False,
                   'checks': {'passed': True}, 'build': {'passed': True}}
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / 'manifest.json').write_text(json.dumps({'stage': 10}))
            with patch.object(cli.evaluate, 'evaluate', return_value=partial) as evaluate:
                code, result = self.command('check', '--level', '10', '--language', 'cpp',
                                            '--source', run / 'main.cpp', '--output', run / 'out')
                self.assertEqual(code, 4)
                self.assertEqual(evaluate.call_args.args[2], 10)
            with patch.object(cli.releases, 'grade', return_value=partial) as grade:
                code, result = self.command('grade', '--run', run, '--performance')
                self.assertEqual(code, 4)
                self.assertTrue(grade.call_args.args[2])
                self.assertTrue((run / 'run.lock').exists())

    def test_publish_stage10_and_reject_conflicting_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, result = self.command('publish', '--level', '10', '--language', 'cpp', '--output', root)
            self.assertEqual(code, 0, result)
            self.assertIn('partial', (root / 'stage-10.md').read_text())
            self.assertEqual(json.loads((root / 'stage-10.json').read_text())['stage'], 10)
            (root / 'manifest.json').write_text(json.dumps({'stage': 10, 'level': 1}))
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                stage_of(root)

    def test_regular_prepare_rejects_luna_and_starter_for_stage10(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'campaign'
            campaign.initialize(root, '2')
            for options in (['--model', 'gpt-6-luna'], ['--starter', 'main.cpp']):
                code, result = self.command('prepare', '--campaign', root, '--level', '10', *options)
                self.assertEqual(code, 1, result)
            self.assertEqual(campaign.read(root)['requests'], [])

    def test_stage10_snapshot_keeps_campaign_accounting_and_scope(self):
        from toksec.result_storage import snapshot_run
        from scripts.refresh_results import select
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            campaign_dir = root / '.runs' / 'campaign'
            campaign.initialize(campaign_dir, '3')
            run = Path(controller.prepare(campaign_dir, 10, language='cpp')['run'])
            manifest = json.loads((run / 'manifest.json').read_text())
            manifest['started_unix'] = 1
            (run / 'manifest.json').write_text(json.dumps(manifest))
            state = json.loads((run / 'state.json').read_text())
            state['finished'] = True
            (run / 'state.json').write_text(json.dumps(state))
            self.assertEqual(select([root])[(10, 'cpp')][0], run)
            destination = root / 'snapshot'
            snapshot_run(run, destination)
            record = json.loads((destination / 'run.json').read_text())
            ledger = json.loads((destination / 'ledger.json').read_text())
            self.assertEqual(record['api_coverage'], 'partial')
            self.assertEqual(record['performance_scope'], 'provisional')
            self.assertEqual(record['budget_usd'], '3')
            self.assertEqual(ledger['parent_campaign'], campaign.read(campaign_dir))
            self.assertEqual(float(ledger['run_allocation_usd']), 2)
            self.assertEqual(ledger['spent_usd_upper_bound'], '0.0')
