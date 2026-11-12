import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from controller import atomic_json
from toksec import campaign, controller, runner
from toksec.benchmark import compare


PARTIAL = r'''
use std::io::{Read,Write};
use std::net::TcpListener;
fn main() {
    let listener=TcpListener::bind("127.0.0.1:8080").unwrap();
    for stream in listener.incoming() {
        if let Ok(mut s)=stream {
            let mut buf=[0u8;16384];
            let n=s.read(&mut buf).unwrap_or(0);
            if n==0 {continue;}
            let text=String::from_utf8_lossy(&buf[..n]);
            let path=text.split_whitespace().nth(1).unwrap_or("/");
            let body=std::fs::read(format!("/www{}",path));
            let (code,data)=match body {Ok(v)=>(200,v),Err(_)=>(404,Vec::new())};
            let _=write!(s,"HTTP/1.1 {} Result\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",code,data.len());
            let _=s.write_all(&data);
        }
    }
}
'''


def response(identity='test-response', tier='default'):
    return {'id': identity, 'model': 'gpt-6-luna', 'service_tier': tier, 'status': 'completed',
            'usage': {'input_tokens': 1100, 'output_tokens': 100, 'total_tokens': 1200}, 'output': []}


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / 'campaign'
        campaign.initialize(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def test_imported_cost_and_shared_sequential_admission(self):
        status = campaign.status(self.directory)
        self.assertEqual(Decimal(status['spent_usd_upper_bound']), Decimal('0.01291213'))
        identity = campaign.reserve(self.directory, 'level-1', 1000)
        with self.assertRaises(ValueError):
            campaign.reserve(self.directory, 'level-2', 1000)
        campaign.settle(self.directory, identity, response())
        campaign.settle(self.directory, identity, response())
        self.assertEqual(campaign.status(self.directory)['used'], status['used'] + 1200)
        self.assertTrue(campaign.status(self.directory)['can_start_model_call'])

    def test_uncertain_usage_remains_reserved(self):
        identity = campaign.reserve(self.directory, 'level-1', 1000)
        with self.assertRaises(ValueError):
            campaign.settle(self.directory, identity, response(tier='priority'))
        self.assertFalse(campaign.status(self.directory)['can_start_model_call'])
        self.assertEqual(campaign.status(self.directory)['reserved'], campaign.RESERVED_TOKENS)

    def test_never_admit_over_either_limit(self):
        ledger = campaign.read(self.directory)
        ledger['token_limit'] = campaign.status(self.directory)['used'] + campaign.RESERVED_TOKENS - 1
        atomic_json(self.directory / 'ledger.json', ledger)
        with self.assertRaises(ValueError):
            campaign.reserve(self.directory, 'level-1', 1)
        ledger['token_limit'] = 10_000_000
        ledger['dollar_limit'] = '0.54'
        atomic_json(self.directory / 'ledger.json', ledger)
        with self.assertRaises(ValueError):
            campaign.reserve(self.directory, 'level-1', 1)

    def test_levels_have_no_candidate_or_context_dependency(self):
        first = Path(controller.prepare(self.directory, 1)['run'])
        second = Path(controller.prepare(self.directory, 2)['run'])
        self.assertFalse(list((first / 'candidates').iterdir()))
        self.assertFalse(list((second / 'candidates').iterdir()))
        self.assertNotIn(str(first), (second / 'launch-packet.md').read_text())
        self.assertEqual(controller.read(first, 'manifest.json')['campaign'], controller.read(second, 'manifest.json')['campaign'])
        self.assertFalse(controller.export(first)['full_acceptance'])
        self.assertIsNone(controller.export(first)['artifact'])

    def test_regression_does_not_replace_retained_artifact(self):
        run = Path(controller.prepare(self.directory, 1)['run'])
        first = controller.submit(run, PARTIAL)
        self.assertTrue(first['retained'])
        self.assertFalse(first['checks']['passed'])
        second = controller.submit(run, 'fn main() { this is not rust }')
        self.assertFalse(second['retained'])
        self.assertEqual(controller.export(run)['best'], first['id'])
        self.assertTrue((run / 'candidates' / first['id'] / 'server').is_file())

    def test_partial_cannot_finish_or_benchmark_while_budget_remains(self):
        run = Path(controller.prepare(self.directory, 1)['run'])
        with self.assertRaises(ValueError):
            runner.dispatch(run, 'finish', {'report': 'done'})
        with self.assertRaises(ValueError):
            runner.dispatch(run, 'benchmark_candidate', {})
        with self.assertRaises(ValueError):
            runner.dispatch(run, 'submit_candidate', {'source': PARTIAL, 'path': '/tmp/escape'})

    def test_deadline_during_validation_preserves_retained_artifact(self):
        run = Path(controller.prepare(self.directory, 1)['run'])
        first = controller.submit(run, PARTIAL)
        with patch('toksec.sandbox.evaluate', side_effect=lambda *args: time.sleep(2)):
            with self.assertRaises(runner.CampaignDeadline):
                with runner.deadline(0.5):
                    controller.submit(run, PARTIAL)
        self.assertEqual(controller.export(run)['best'], first['id'])

    def test_fake_api_loop_uses_sandbox_and_retains_working_result(self):
        run = Path(controller.prepare(self.directory, 1)['run'])
        requests = []
        class Client:
            def post(self, endpoint, payload, timeout):
                if endpoint == 'responses/input_tokens':
                    return {'input_tokens': 1000}
                requests.append(payload)
                result = response(str(len(requests)))
                if len(requests) <= 2:
                    source = PARTIAL if len(requests) == 1 else 'broken rust'
                    result['output'] = [{'type': 'function_call', 'call_id': str(len(requests)), 'name': 'submit_candidate',
                                         'arguments': json.dumps({'source': source})}]
                if len(requests) == 3:
                    manifest = controller.read(run, 'manifest.json')
                    manifest['started_unix'] = time.time() - 1700
                    atomic_json(run / 'manifest.json', manifest)
                return result
        result = runner.run_loop(run, Client())
        self.assertIsNotNone(result['artifact'])
        self.assertFalse(result['full_acceptance'])
        self.assertTrue(all(r['service_tier'] == 'default' for r in requests))
        self.assertIn('public-suite/checks.py', requests[0]['input'][0]['content'])
        self.assertEqual(len([r for r in campaign.read(self.directory)['requests'] if r['run'] == run.name]), 3)

    def test_timeout_preserves_reservation_and_exports_without_retry(self):
        run = Path(controller.prepare(self.directory, 1)['run'])
        class Client:
            def post(self, endpoint, payload, timeout):
                if endpoint.endswith('input_tokens'):
                    return {'input_tokens': 1000}
                raise TimeoutError('simulated lost response')
        result = runner.run_loop(run, Client())
        self.assertIsNone(result['artifact'])
        self.assertEqual(campaign.status(self.directory)['reserved'], campaign.RESERVED_TOKENS)
        self.assertFalse(campaign.status(self.directory)['can_start_model_call'])


class ComparisonTests(unittest.TestCase):
    def test_only_complete_error_free_improvements_promote(self):
        old = {'one': {'eligible': True, 'failures': 0, 'worst_p99_ms': 10, 'min_rps': 98, 'max_rps': 102, 'median_rps': 100}}
        new = {'one': dict(old['one'], min_rps=110, max_rps=114, median_rps=112)}
        self.assertTrue(compare(old, new)['promote'])
        for change in ({'eligible': False}, {'failures': 1}, {'worst_p99_ms': 11}, {'min_rps': 101}):
            self.assertFalse(compare(old, {'one': dict(new['one'], **change)})['promote'])
        self.assertFalse(compare(old, {})['promote'])
