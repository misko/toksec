import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import atomic_json
from test_campaign import PARTIAL, response
from toksec import campaign, context, controller, runner


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.campaign = Path(self.temp.name) / 'campaign'
        campaign.initialize(self.campaign)
        self.run = Path(controller.prepare(self.campaign, 1)['run'])

    def tearDown(self):
        self.temp.cleanup()

    def test_acceptance_and_many_optimizations_do_not_allow_early_finish(self):
        state = controller.read(self.run)
        state.update(full_acceptance=True, optimization_attempts=99)
        atomic_json(self.run / 'state.json', state)
        self.assertFalse(controller.capacity(self.run)['can_finish'])
        with self.assertRaisesRegex(ValueError, 'Capacity remains'):
            runner.dispatch(self.run, 'finish', {'report': 'minimum complete'})
        self.assertFalse((self.run / 'model-report.md').exists())

    def test_finalization_window_allows_honest_partial_report(self):
        manifest = controller.read(self.run, 'manifest.json')
        manifest['started_unix'] = time.time() - 1700
        atomic_json(self.run / 'manifest.json', manifest)
        self.assertTrue(controller.capacity(self.run)['can_finish'])
        self.assertTrue(runner.dispatch(self.run, 'finish', {'report': 'No accepted artifact.'})['finished'])

    def test_rollover_keeps_code_and_notes_without_resetting_spending(self):
        accepted = controller.submit(self.run, PARTIAL)
        broken = controller.submit(self.run, 'broken rust')
        entry = {'category': 'security', 'hypothesis': 'Test overflow boundaries', 'change': 'None yet',
                 'evidence': 'No test yet', 'verdict': 'unverified', 'next_action': 'run_tests'}
        runner.dispatch(self.run, 'record_iteration', entry)
        before = campaign.read(self.campaign)
        history = context.checkpoint(self.run, 'frozen contract')
        data = json.loads(history[1]['content'])
        self.assertEqual({c['id'] for c in data['candidates']}, {accepted['id'], broken['id']})
        self.assertIn(PARTIAL, [c['source'] for c in data['candidates']])
        self.assertEqual(data['model_authored_journal'][0]['hypothesis'], entry['hypothesis'])
        self.assertEqual(campaign.read(self.campaign), before)
        self.assertEqual(controller.read(self.run)['context_rollovers'], 1)
        self.assertEqual(controller.read(self.run)['best'], accepted['id'])

    def test_overflow_compacts_before_paid_dispatch_and_plain_final_does_not_stop_early(self):
        run = self.run
        counts = []
        calls = []
        class Client:
            def post(self, endpoint, payload, timeout):
                if endpoint.endswith('input_tokens'):
                    counts.append(payload)
                    return {'input_tokens': 65000 if len(counts) == 1 else 20000}
                calls.append(payload)
                result = response(f'new-{len(calls)}')
                result['output'] = [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'I am done'}]}]
                if len(calls) == 2:
                    manifest = controller.read(run, 'manifest.json')
                    manifest['started_unix'] = time.time() - 1700
                    atomic_json(run / 'manifest.json', manifest)
                return result
        result = runner.run_loop(run, Client())
        self.assertEqual(len(calls), 2)
        self.assertEqual(controller.read(run)['context_rollovers'], 1)
        self.assertEqual(result['state']['stop_reason'], 'finished')
        self.assertTrue(all(c['service_tier'] == 'default' for c in calls))
        entries = [r for r in campaign.read(self.campaign)['requests'] if r['run'] == run.name]
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(r['counted_input'] == 20000 for r in entries))

    def test_restart_failure_invalidates_old_acceptance_and_can_be_repaired(self):
        first = controller.submit(self.run, PARTIAL)
        good = {'passed': True, 'cases': [{'id': 'bootstrap', 'passed': True}]}
        with patch('toksec.sandbox.evaluate', side_effect=[good, RuntimeError('thread spawn failure'), good]):
            result = controller.revalidate(self.run, 'incumbent')
        self.assertFalse(result['passed'])
        self.assertIn(first['id'], controller.read(self.run)['invalidated'])
        self.assertIn('failed revalidation', controller.export(self.run)['warning'])
        with patch('toksec.sandbox.evaluate', return_value=good):
            repaired = controller.submit(self.run, PARTIAL)
        self.assertEqual(controller.read(self.run)['best'], repaired['id'])
        self.assertIsNone(controller.export(self.run)['warning'])

    def test_framework_upgrade_preserves_usage_and_rejects_uncertain_charges(self):
        identity = campaign.reserve(self.campaign, self.run.name, 1000)
        with self.assertRaises(ValueError):
            campaign.upgrade(self.campaign)
        campaign.settle(self.campaign, identity, response())
        before = campaign.read(self.campaign)
        with patch('toksec.campaign.fingerprint', return_value='new-framework'):
            campaign.upgrade(self.campaign)
        after = campaign.read(self.campaign)
        self.assertEqual(after['requests'], before['requests'])
        self.assertEqual(after['token_limit'], before['token_limit'])
        self.assertEqual(after['dollar_limit'], before['dollar_limit'])
        self.assertEqual(after['framework_upgrades'][-1]['previous'], before['fingerprint'])
        self.assertEqual(after['fingerprint'], 'new-framework')
