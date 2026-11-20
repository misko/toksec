import datetime
import contextlib
import io
import json
from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

from toksec import batch, campaign, controller, gateway_turn, runner
from toksec.api import ProviderHTTPError
from toksec.storage import atomic_json


class PowerLoss(BaseException):
    """A process death bypasses the runner's graceful error handler."""


class LocalProvider:
    def __init__(self, outputs, *, count_failures=0):
        self.outputs = iter(outputs)
        self.sends = []
        self.counts = 0
        self.count_failures = count_failures

    def post(self, endpoint, body, timeout):
        if endpoint.endswith('input_tokens'):
            self.counts += 1
            if self.counts <= self.count_failures:
                raise TimeoutError('input count connection lost')
            return {'input_tokens': 1000}
        self.sends.append((body, timeout))
        result = next(self.outputs)
        if isinstance(result, BaseException):
            raise result
        return result


def terminal(identity='r1', name='budget_status', arguments=None):
    return {'id': identity, 'model': campaign.TERRA, 'service_tier': 'default', 'status': 'completed',
            'usage': {'input_tokens': 1000, 'output_tokens': 50, 'total_tokens': 1050},
            'output': [{'type': 'function_call', 'call_id': identity + '-tool', 'name': name,
                        'arguments': json.dumps(arguments or {})}]}


class GatewayRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.campaign = Path(self.temp.name) / 'campaign'
        self.use_patch(patch.object(controller, 'checkout', return_value={'toksec_commit': 'a' * 40, 'toksec_dirty': False}))
        # The transport is a fixture. Make freshness deterministic without modifying any measured launch.
        self.use_patch(patch.object(runner.metering, 'PRICE_DATE', datetime.datetime.now(datetime.timezone.utc).date().isoformat()))
        campaign.initialize(self.campaign, '3', request_profile='bounded-32k')
        self.run = Path(controller.prepare(self.campaign, 14, 7200, campaign.TERRA, language='cpp')['run'])

    def use_patch(self, mock):
        self.addCleanup(mock.stop)
        return mock.start()

    def status(self):
        return runner.recovery_status(self.run)

    def entries(self):
        return campaign.read(self.campaign)['requests']

    def test_unknown_generation_cannot_be_resent_or_refunded(self):
        provider = LocalProvider([TimeoutError('read timeout')])
        result = runner.run_loop(self.run, provider)
        self.assertEqual(result['state']['stop_kind'], 'generation_timeout')
        self.assertEqual(len(provider.sends), 1)
        self.assertEqual(provider.sends[0][1], 300)
        observed = self.status()
        self.assertEqual(observed['phase'], 'generation_outcome_unknown')
        self.assertFalse(observed['continuation_possible'])
        self.assertEqual(Decimal(observed['held_usd']), Decimal('.2'))
        self.assertEqual(gateway_turn.digest(provider.sends[0][0]), self.entries()[0]['request_sha256'])
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, 'unresolved generation'):
                runner.run_loop(self.run, provider, resume=True)
            self.assertEqual(runner.recovery_status(self.run, settle=True)['held_usd'], observed['held_usd'])
        self.assertEqual(len(provider.sends), 1)
        self.assertEqual(self.status()['deadline_unix'], observed['deadline_unix'])

    def test_locally_saved_response_reconciles_twice_before_next_send(self):
        provider = LocalProvider([terminal('previous'), TimeoutError('second generation')])
        with patch.object(campaign, 'settle', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        status = self.status()
        self.assertEqual(status['phase'], 'response_saved')
        for _ in range(2):
            offline = runner.recovery_status(self.run, settle=True)
            self.assertEqual(Decimal(offline['held_usd']), 0)
            self.assertTrue(offline['continuation_possible'])
        self.assertEqual(len(provider.sends), 1)
        with patch.object(runner, 'dispatch', wraps=runner.dispatch) as dispatch:
            runner.run_loop(self.run, provider, resume=True)
            dispatch.assert_called_once()
        self.assertEqual(len(provider.sends), 2)
        self.assertEqual(self.entries()[0]['response_id'], 'previous')
        self.assertEqual(self.status()['deadline_unix'], status['deadline_unix'])

    def test_expired_deadline_still_settles_saved_response_offline(self):
        provider = LocalProvider([terminal()])
        with patch.object(campaign, 'settle', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        limit = self.status()['deadline_unix']
        with patch('time.time', return_value=limit + 1):
            self.assertFalse(runner.recovery_status(self.run, settle=True)['continuation_possible'])
            with self.assertRaisesRegex(ValueError, 'original run deadline'):
                runner.run_loop(self.run, provider, resume=True)
        self.assertEqual(len(provider.sends), 1)
        self.assertEqual(self.entries()[0]['state'], 'settled')

    def test_corrupt_response_retains_full_hold(self):
        provider = LocalProvider([terminal()])
        with patch.object(campaign, 'settle', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        path = next(self.run.glob('response-*.json'))
        response = json.loads(path.read_text())
        response['usage'] = {'input_tokens': 999, 'output_tokens': 50, 'total_tokens': 1049}
        atomic_json(path, response)
        with self.assertRaisesRegex(ValueError, 'unreconciled'):
            runner.recovery_status(self.run, settle=True)
        self.assertEqual(self.entries()[0]['state'], 'reserved')
        self.assertEqual(len(provider.sends), 1)

    def test_saved_tool_receipt_prevents_a_second_dispatch(self):
        provider = LocalProvider([terminal(), PowerLoss()])
        original = runner._prepare_turn
        def next_turn(*args):
            if list(self.run.glob('tool-*.json')):
                raise PowerLoss()
            return original(*args)
        with patch.object(runner, 'dispatch', wraps=runner.dispatch) as dispatch:
            with patch.object(runner, '_prepare_turn', side_effect=next_turn):
                with self.assertRaises(PowerLoss):
                    runner.run_loop(self.run, provider)
            self.assertEqual(self.status()['phase'], 'tool_receipt_saved')
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider, resume=True)
            dispatch.assert_called_once()
        self.assertEqual(len(provider.sends), 2)

    def test_lost_mutating_tool_receipt_quarantines_the_action(self):
        from test_cpp import SERVER
        provider = LocalProvider([terminal('build', 'submit_candidate', {'source': SERVER}),
                                  terminal('tag', 'init_repository')])
        def lose_after_tag(run, name, args):
            result = original(run, name, args)
            if name == 'init_repository':
                raise PowerLoss()
            return result
        original = runner.dispatch
        with patch.object(runner, 'dispatch', side_effect=lose_after_tag):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        observed = self.status()
        self.assertEqual(observed['phase'], 'tool_outcome_unknown')
        self.assertEqual(observed['latest_release']['tag'], 'release/000001')
        with self.assertRaisesRegex(ValueError, 'unresolved tool'):
            runner.run_loop(self.run, provider, resume=True)
        self.assertEqual(len(provider.sends), 2)
        self.assertEqual(len(runner.releases.list_releases(self.run)), 1)

    def test_interruption_before_reservation_allows_one_first_send(self):
        provider = LocalProvider([TimeoutError('read timeout')])
        with patch.object(campaign, 'reserve', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.status()['phase'], 'counted_before_reservation')
        runner.run_loop(self.run, provider, resume=True)
        self.assertEqual(provider.counts, 1)
        self.assertEqual(len(provider.sends), 1)
        self.assertEqual(len(self.entries()), 1)

    def test_reserved_but_unsent_can_be_dispatched_once(self):
        provider = LocalProvider([TimeoutError('after dispatch')])
        with patch.object(campaign, 'begin_send', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        self.assertEqual(len(provider.sends), 0)
        self.assertEqual(self.status()['phase'], 'reserved_before_dispatch')
        runner.run_loop(self.run, provider, resume=True)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(len(provider.sends), 1)
        self.assertEqual(self.status()['phase'], 'generation_outcome_unknown')

    def test_expired_never_dispatched_hold_can_be_released(self):
        provider = LocalProvider([])
        with patch.object(campaign, 'begin_send', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                runner.run_loop(self.run, provider)
        deadline = self.status()['deadline_unix']
        with patch('time.time', return_value=deadline + 1):
            for _ in range(2):
                recovery = runner.recovery_status(self.run, settle=True)
                self.assertEqual(recovery['phase'], 'cancelled_before_send')
                self.assertEqual(Decimal(recovery['held_usd']), 0)
        self.assertEqual(len(provider.sends), 0)

    def test_cli_completes_a_150_second_generation_and_recovery_is_offline(self):
        from toksec.__main__ import main
        clock = [time.time()]
        calls = []
        def transport(client, endpoint, body, timeout, **kwargs):
            if endpoint.endswith('input_tokens'):
                return {'input_tokens': 1000}
            calls.append(kwargs['request_id'])
            if timeout < 150:
                raise TimeoutError('simulated response takes 150 seconds')
            clock[0] += 150
            result = terminal()
            result['output'] = []
            return result
        m = controller.read(self.run, 'manifest.json')
        m['wall_seconds'] = 270
        atomic_json(self.run / 'manifest.json', m)
        with patch('time.time', side_effect=lambda:clock[0]), patch.object(runner.Responses, 'post', transport), patch.object(
                runner, 'credentials', return_value='local-test-transport'):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['run','--run',str(self.run)]), 0)
            record = json.loads(out.getvalue())
            self.assertEqual(record['state']['stop_reason'], 'finished')
            self.assertEqual(record['capacity']['seconds_remaining'], 120)
            self.assertEqual(record['capacity']['reserved_usd'], '0')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['recover','--run',str(self.run),'--settle']), 0)
        self.assertEqual(len(calls), 1)

    def test_safe_count_retry_sends_one_generation_with_long_timeout(self):
        provider = LocalProvider([terminal(), TimeoutError('after first completion')], count_failures=1)
        with patch.object(time, 'sleep'):
            runner.run_loop(self.run, provider)
        self.assertEqual(provider.counts, 3)
        self.assertEqual(len(provider.sends), 2)
        self.assertTrue(all(timeout >= 150 for _, timeout in provider.sends))
        self.assertEqual([e['state'] for e in self.entries()], ['settled', 'reserved'])

    def test_only_one_owner_may_resume(self):
        provider = LocalProvider([])
        with campaign.locked(self.campaign, owner=True):
            with self.assertRaises(BlockingIOError):
                runner.run_loop(self.run, provider, resume=True)
        self.assertFalse(provider.sends)

    def test_provider_errors_distinct_from_server_responses(self):
        http = urllib.error.HTTPError('https://example.invalid', 429, 'hidden', {'x-request-id': 'provider-rid', 'retry-after':'120'}, None)
        result = runner.run_loop(self.run, LocalProvider([ProviderHTTPError('responses', http)]))
        state = result['state']
        self.assertEqual(state['stop_metadata']['provider_request_id'], 'provider-rid')
        self.assertEqual(state['stop_metadata']['retry_after'], '120')
        http.close()
        job = {'run': str(self.run), 'campaign': str(self.campaign)}
        queue = {}
        self.assertEqual(batch.observe_builder(job, queue), 'API HTTP 429')
        self.assertEqual(job['held_usd'], '0.200')
        state.update(stop_kind='finished', stop_reason='candidate server returned HTTP 429')
        atomic_json(self.run / 'state.json', state)
        self.assertIsNone(batch.observe_builder(job, queue))
        state.update(stop_kind='generation_timeout', stop_reason='read timeout')
        atomic_json(self.run / 'state.json', state)
        self.assertIsNone(batch.observe_builder(job, queue))
        self.assertEqual(batch.observe_builder(job, queue), 'two consecutive generation timeouts')


if __name__ == '__main__':
    unittest.main()
