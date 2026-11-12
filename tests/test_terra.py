import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from controller import atomic_json
from toksec import campaign, controller, runner


class TerraTests(unittest.TestCase):
    def test_mixed_model_costs_and_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'campaign'
            campaign.initialize(directory)
            before = campaign.status(directory)
            selected = campaign.status(directory, campaign.TERRA)
            self.assertEqual(Decimal(selected['next_call_reservation_usd']), Decimal('2.745'))
            identity = campaign.reserve(directory, 'terra', 1100, campaign.TERRA)
            campaign.settle(directory, identity, {'id': 'terra-response', 'model': campaign.TERRA,
                'service_tier': 'default', 'status': 'completed',
                'usage': {'input_tokens': 1100, 'output_tokens': 100, 'total_tokens': 1200}})
            after = campaign.status(directory)
            self.assertEqual(Decimal(after['spent_usd_upper_bound']) - Decimal(before['spent_usd_upper_bound']), Decimal('.001875'))
            ledger = campaign.read(directory)
            ledger['dollar_limit'] = '2.00'
            atomic_json(directory / 'ledger.json', ledger)
            self.assertFalse(campaign.status(directory, campaign.TERRA)['can_start_model_call'])
            with self.assertRaises(ValueError):
                campaign.reserve(directory, 'terra', 1100, campaign.TERRA)

    def test_manifest_records_medium_and_cache_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'campaign'
            campaign.initialize(directory)
            run = controller.prepare(directory, 1, model=campaign.TERRA)['run']
            manifest = controller.read(run, 'manifest.json')
            self.assertEqual(manifest['model'], campaign.TERRA)
            self.assertEqual(manifest['reasoning_effort'], 'medium')
            self.assertEqual(manifest['billing_profile']['prompt_cache_options']['ttl'], '30m')
            self.assertEqual(controller.capacity(run)['model'], campaign.TERRA)

    def test_generation_explicitly_sets_model_reasoning_tier_and_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'campaign'
            campaign.initialize(directory)
            run = Path(controller.prepare(directory, 2, model=campaign.TERRA)['run'])
            sent = []
            class Client:
                def post(self, endpoint, payload, timeout):
                    if endpoint.endswith('input_tokens'):
                        return {'input_tokens': 1100}
                    sent.append(payload)
                    manifest = controller.read(run, 'manifest.json')
                    manifest['started_unix'] = time.time() - 1700
                    atomic_json(run / 'manifest.json', manifest)
                    return {'id': 'terra-request', 'model': campaign.TERRA,
                            'service_tier': 'default', 'status': 'completed', 'output': [],
                            'usage': {'input_tokens': 1100, 'output_tokens': 100, 'total_tokens': 1200}}
            runner.run_loop(run, Client())
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]['model'], campaign.TERRA)
            self.assertEqual(sent[0]['reasoning'], {'effort': 'medium'})
            self.assertEqual(sent[0]['service_tier'], 'default')
            self.assertEqual(sent[0]['prompt_cache_options'], {'mode': 'implicit', 'ttl': '30m'})
