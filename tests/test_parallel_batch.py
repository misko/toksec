import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from toksec import batch, campaign, controller, runner
from toksec.accounting.counted_requests import validate_request, COUNT_FIELDS


class BatchTests(unittest.TestCase):
    def test_prepare_cli_creates_fresh_bounded_campaign_without_api_calls(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(tmp) / 'batch'
            result = batch.main(['prepare', '--directory', str(directory), '--stages', '1',
                                 '--replicas', '1', '--parallel', '1', '--budget-usd', '2'])
            self.assertEqual(result, 0)
            prepared = batch.read(directory / 'batch.json')
            self.assertEqual(prepared['status'], 'prepared')
            job = prepared['jobs'][0]
            ledger = campaign.read(job['campaign'])
            self.assertEqual(ledger['request_profile'], 'bounded-32k')
            self.assertEqual(ledger['requests'], [])
            self.assertIsNone(controller.read(job['run'], 'manifest.json')['started_unix'])

    def test_budget_sweep_has_nine_independent_jobs_and_explicit_stage10_caps(self):
        import contextlib
        import io
        value = batch.plan([1, 5, 10], 1, 1, None, 7200, 'cpp', list(range(6)), budgets_usd=['3', '4', '5'])
        self.assertEqual(value['total_cap_usd'], '36')
        self.assertEqual(len({j['id'] for j in value['jobs']}), 9)
        self.assertEqual({(j['stage'], j['budget_usd']) for j in value['jobs']},
                         {(stage, budget) for stage in (1, 5, 10) for budget in ('3', '4', '5')})
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(tmp) / 'batch'
            result = batch.main(['prepare', '--directory', str(directory), '--stages', '10',
                                 '--replicas', '1', '--parallel', '1', '--budgets-usd', '3', '4', '5'])
            self.assertEqual(result, 0)
            for job in batch.read(directory / 'batch.json')['jobs']:
                manifest = controller.read(job['run'], 'manifest.json')
                self.assertEqual(manifest['budget_usd'], job['budget_usd'])
                self.assertEqual(campaign.read(job['campaign'])['requests'], [])
        with self.assertRaises(ValueError):
            batch.plan([1], 1, 1, None, 7200, 'cpp', list(range(6)), budgets_usd=['3', '3.0'])
        with self.assertRaises(ValueError):
            batch.plan([1], 1, 1, '5.01', 7200, 'cpp', list(range(6)))

    def test_plan_has_independent_caps_and_disjoint_slots(self):
        plan = batch.plan([1, 5, 10], 3, 3, '2', 7200, 'cpp', list(range(24)))
        self.assertEqual(plan['total_cap_usd'], '18')
        self.assertEqual(len(plan['jobs']), 9)
        self.assertEqual(len({j['id'] for j in plan['jobs']}), 9)
        self.assertTrue(set(plan['jobs'][0]['cpus']).isdisjoint(plan['jobs'][1]['cpus']))
        self.assertTrue(all(j['budget_usd'] == '2' for j in plan['jobs']))
        with self.assertRaises(ValueError):
            batch.plan([1, 5, 10], 3, 3, '2', 7200, 'cpp', list(range(12)))

    def test_scheduler_reuses_slots_without_overlap_or_duplicate_starts(self):
        jobs = batch.plan([1, 5, 10], 3, 3, '2', 7200, 'cpp', list(range(18)))['jobs']
        for job in jobs: job['status'] = 'prepared'
        active = set(); started = []; high = []
        class Process:
            def __init__(self, job):
                self.job = job; self.pid = len(started); self.polls = 0
            def poll(self):
                self.polls += 1
                if self.polls == 2:
                    active.remove(self.job['slot'])
                    return 0
                return None
        def start(job):
            self.assertNotIn(job['slot'], active)
            active.add(job['slot']); started.append(job['id']); high.append(len(active))
            return Process(job)
        batch.schedule(jobs, 3, start, lambda: None, poll_seconds=0)
        self.assertEqual(max(high), 3)
        self.assertEqual(len(set(started)), 9)
        self.assertTrue(all(j['status'] == 'builder_stopped' for j in jobs))

    def test_ineligible_performance_is_still_published(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); run = directory / 'run'; run.mkdir()
            value = {'jobs': [{'run': str(run), 'cpus': [0], 'status': 'builder_stopped'}]}
            with patch('toksec.batch.capture', return_value={'releases': [{'tag': 'release/000001'}]}), patch(
                    'toksec.batch.subprocess.run', side_effect=[SimpleNamespace(returncode=3), SimpleNamespace(returncode=0)]):
                result = batch.finalize(directory, value, directory / 'results')
            self.assertEqual(result['jobs'][0]['grade_exit_code'], 3)
            self.assertEqual(result['jobs'][0]['status'], 'complete')

    def test_paid_resume_is_rejected_before_credentials_or_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'batch.json').write_text(json.dumps({'status': 'running', 'jobs': []}))
            with patch('toksec.runner.credentials') as credentials, self.assertRaisesRegex(ValueError, 'resume'):
                batch.launch(path, '/missing', path / 'results')
            credentials.assert_not_called()


class BoundedRequestTests(unittest.TestCase):
    def test_reservation_fits_two_dollars_and_retains_uncertain_charge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'campaign'
            campaign.initialize(path, '2', request_profile='bounded-32k')
            before = campaign.status(path)
            self.assertEqual(before['next_call_reservation_usd'], '0.200')
            self.assertEqual(before['next_call_reservation_tokens'], 48000)
            with self.assertRaises(ValueError):
                campaign.reserve(path, 'test', 32001, campaign.TERRA)
            identity = campaign.reserve(path, 'test', 32000, campaign.TERRA)
            with self.assertRaises(ValueError):
                campaign.reserve(path, 'another', 1000, campaign.TERRA)
            self.assertEqual(campaign.status(path)['reserved'], 48000)
            self.assertFalse(campaign.status(path)['can_start_model_call'])
            self.assertEqual(campaign.read(path)['requests'][0]['id'], identity)

    def test_exact_counted_plain_request_is_sent_without_encrypted_reasoning(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'campaign'
            campaign.initialize(directory, '2', request_profile='bounded-32k')
            run = Path(controller.prepare(directory, 1, model=campaign.TERRA, language='cpp')['run'])
            counted = []; sent = []
            class Client:
                def post(self, endpoint, payload, timeout):
                    if endpoint.endswith('input_tokens'):
                        counted.append(payload.copy())
                        return {'input_tokens': 1000}
                    validate_request(payload)
                    sent.append(payload.copy())
                    self_outer.assertEqual(counted[-1], {k: v for k, v in payload.items() if k in COUNT_FIELDS})
                    self_outer.assertNotIn('include', payload)
                    if len(sent) == 2:
                        raise TimeoutError('uncertain response')
                    return {'id': 'bounded-one', 'model': campaign.TERRA, 'service_tier': 'default',
                            'status': 'completed', 'usage': {'input_tokens': 1000, 'output_tokens': 10, 'total_tokens': 1010},
                            'output': [{'type': 'reasoning', 'encrypted_content': 'must-not-be-replayed'},
                                       {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Continue'}]}]}
            self_outer = self
            runner.run_loop(run, Client())
            self.assertEqual(len(sent), 2)
            self.assertNotIn('must-not-be-replayed', json.dumps(sent[1]))
            self.assertFalse(campaign.status(directory)['can_start_model_call'])
            self.assertLessEqual(float(campaign.status(directory)['spent_usd_upper_bound']) + float(campaign.status(directory)['reserved_usd']), 2)
