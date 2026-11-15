import contextlib
import datetime
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec import controller
from toksec.execution import counted as child_runner
from toksec.accounting.counted_requests import BudgetLedger, MODEL
from toksec import campaign
from toksec.accounting import run_allocations as stage10_campaign
from toksec.storage import atomic_json


class Stage10CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'campaign'
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(campaign, 'fingerprint', return_value='f' * 64))
        self.stack.enter_context(patch.object(stage10_campaign, 'fingerprint', return_value='f' * 64))
        self.stack.enter_context(patch.object(controller, 'counted_fingerprint', return_value='a' * 64))
        clock = self.stack.enter_context(patch('toksec.accounting.run_allocations.datetime.datetime'))
        clock.now.return_value.date.return_value = datetime.date(2026, 11, 15)
        self.stack.enter_context(patch('toksec.accounting.run_allocations.shutil.which', return_value='/bin/tool'))
        self.stack.enter_context(patch('toksec.accounting.run_allocations.resource.getrlimit', return_value=(16384, 16384)))
        campaign.initialize(self.root, '3')

    def prepare(self, amount=None):
        result = stage10_campaign.prepare(self.root, language='cpp', spend_target_usd=amount)
        return Path(result['run'])

    def payload(self):
        return {'model': MODEL, 'service_tier': 'default', 'store': False,
                'truncation': 'disabled', 'reasoning': {'effort': 'medium'},
                'prompt_cache_options': {'mode': 'implicit', 'ttl': '30m'},
                'input': [{'role': 'user', 'content': 'test'}], 'max_output_tokens': 1000}

    def spend(self, run, uncertain=False):
        manifest = controller.read(run, 'manifest.json')
        manifest['started_unix'] = 1
        atomic_json(run / 'manifest.json', manifest)
        ledger = BudgetLedger(run / 'budget.sqlite', manifest['budget_usd'])
        def send(body):
            parent = campaign.read(self.root)
            self.assertEqual(parent['requests'][-1]['state'], 'reserved')
            self.assertFalse(campaign.status(self.root)['can_start_model_call'])
            self.assertFalse(stage10_campaign.status(self.root)['can_start_model_call'])
            if uncertain:
                raise TimeoutError('unknown provider response')
            return {'model': MODEL, 'service_tier': 'default', 'status': 'completed',
                    'usage': {'input_tokens': 1000, 'output_tokens': 1000}}
        try:
            ledger.execute(self.payload(),
                           lambda body: {'object': 'response.input_tokens', 'input_tokens': 1000}, send)
        except TimeoutError:
            pass
        state = controller.read(run); state['finished'] = True
        atomic_json(run / 'state.json', state)
        return {'finished': True}

    def test_preparation_does_not_reserve_or_spend(self):
        run = self.prepare()
        self.assertEqual(campaign.read(self.root)['requests'], [])
        manifest = controller.read(run, 'manifest.json')
        self.assertEqual(manifest['campaign_backend'], stage10_campaign.BACKEND)
        self.assertEqual(manifest['campaign_total_cap_usd'], '3')
        self.assertEqual(Decimal(manifest['budget_usd']), Decimal(2))
        self.assertTrue(stage10_campaign.preflight(run)['launch_allowed'])

    def test_parent_reserves_before_child_and_refunds_unused_after_settlement(self):
        run = self.prepare()
        with patch.object(child_runner, '_locked_run_loop', side_effect=lambda r, c: self.spend(r)):
            result = stage10_campaign.run_loop(run, object())
        parent = campaign.read(self.root); entry = parent['requests'][-1]
        self.assertEqual(entry['state'], 'settled')
        self.assertEqual(entry['reserved_tokens'], 1_600_000)
        self.assertEqual(entry['usage']['total'], 2000)
        self.assertEqual(Decimal(entry['usage']['cost_usd_upper_bound']), Decimal('0.00625'))
        self.assertEqual(Decimal(result['campaign_accounting']['remaining_usd']), Decimal('2.99375'))
        self.assertFalse(stage10_campaign.preflight(run)['launch_allowed'])

    def test_uncertain_child_keeps_entire_parent_hold(self):
        run = self.prepare()
        with patch.object(child_runner, '_locked_run_loop', side_effect=lambda r, c: self.spend(r, True)):
            stage10_campaign.run_loop(run, object())
        parent = campaign.read(self.root); entry = parent['requests'][-1]
        self.assertEqual(parent['state'], 'uncertain')
        self.assertEqual(entry['state'], 'reserved')
        self.assertEqual(Decimal(entry['reserved_usd']), Decimal(2))
        self.assertTrue(stage10_campaign.status(self.root)['has_pending_allocation'])
        self.assertFalse(campaign.status(self.root)['can_start_model_call'])
        with self.assertRaises(ValueError):
            self.prepare()

    def test_parent_token_limit_restricts_child_budget(self):
        ledger = campaign.read(self.root); ledger['token_limit'] = 100_000
        atomic_json(self.root / 'ledger.json', ledger)
        run = self.prepare()
        manifest = controller.read(run, 'manifest.json')
        self.assertEqual(Decimal(manifest['budget_usd']), Decimal('0.125'))
        with patch.object(child_runner, '_locked_run_loop', side_effect=lambda r, c: self.spend(r)):
            stage10_campaign.run_loop(run, object())
        self.assertEqual(campaign.read(self.root)['requests'][-1]['reserved_tokens'], 100_000)

    def test_stale_prepared_allocation_cannot_oversubscribe_parent(self):
        run = self.prepare()
        ledger = campaign.read(self.root)
        ledger['requests'].append({'id': 'prior', 'run': 'prior', 'state': 'settled',
                                   'usage': {'total': 1, 'cost_usd_upper_bound': '1.5'}})
        atomic_json(self.root / 'ledger.json', ledger)
        with patch.object(child_runner, '_locked_run_loop') as invoke:
            with self.assertRaises(ValueError):
                stage10_campaign.run_loop(run, object())
        invoke.assert_not_called()
        self.assertEqual(len(campaign.read(self.root)['requests']), 1)

    def test_rejects_unsupported_model_budget_and_profile_tampering(self):
        with self.assertRaises(ValueError):
            stage10_campaign.prepare(self.root, model='gpt-6-luna')
        for amount in ('3', 'NaN', '-1', 'not-a-number'):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.prepare(amount)
        run = self.prepare('1')
        manifest = controller.read(run, 'manifest.json'); manifest['budget_usd'] = '2'
        atomic_json(run / 'manifest.json', manifest)
        self.assertFalse(stage10_campaign.preflight(run)['launch_allowed'])

    def test_existing_reservation_blocks_run_even_if_manifest_was_reset(self):
        run = self.prepare()
        stage10_campaign._reserve(run, self.root, Decimal('2'))
        with patch.object(child_runner, '_locked_run_loop') as invoke:
            with self.assertRaises(ValueError):
                stage10_campaign.run_loop(run, object())
        invoke.assert_not_called()

    def test_exception_after_known_child_usage_still_reconciles(self):
        run = self.prepare()
        def fail(r, client):
            self.spend(r)
            raise RuntimeError('post-run reporting failed')
        with patch.object(child_runner, '_locked_run_loop', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'reporting failed'):
                stage10_campaign.run_loop(run, object())
        self.assertEqual(campaign.read(self.root)['requests'][-1]['state'], 'settled')

    def test_missing_child_ledger_cannot_be_recreated_to_erase_usage(self):
        run = self.prepare(); (run / 'budget.sqlite').unlink()
        with patch.object(child_runner, '_locked_run_loop') as invoke:
            with self.assertRaises(ValueError):
                stage10_campaign.run_loop(run, object())
        invoke.assert_not_called()

    def test_lost_child_ledger_after_launch_keeps_parent_reservation(self):
        run = self.prepare()
        def lose(r, client):
            self.spend(r)
            (r / 'budget.sqlite').unlink()
            return {'finished': True}
        with patch.object(child_runner, '_locked_run_loop', side_effect=lose):
            stage10_campaign.run_loop(run, object())
        self.assertEqual(campaign.read(self.root)['state'], 'uncertain')
        self.assertEqual(campaign.read(self.root)['requests'][-1]['state'], 'reserved')
        self.assertFalse((run / 'budget.sqlite').exists())
