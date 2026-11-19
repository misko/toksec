import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from toksec.api import NoRedirect, Responses
from toksec import metering
from toksec.storage import atomic_json


class StorageTests(unittest.TestCase):
    def test_replacement_is_complete_and_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'record.json'
            destination.write_text('old contents')
            atomic_json(destination, {'z': [1, 2], 'a': True})
            self.assertEqual(json.loads(destination.read_text()), {'a': True, 'z': [1, 2]})
            self.assertTrue(destination.read_text().endswith('\n'))
            self.assertEqual(list(Path(tmp).iterdir()), [destination])

    def test_serialization_failure_preserves_previous_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'record.json'
            destination.write_text('{"old": true}\n')
            with self.assertRaises(TypeError):
                atomic_json(destination, {'invalid': object()})
            self.assertEqual(destination.read_text(), '{"old": true}\n')
            self.assertEqual(list(Path(tmp).iterdir()), [destination])


class ApiTransportTests(unittest.TestCase):
    def test_single_request_uses_fixed_endpoint_and_exact_payload(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"id":"response-example"}')
        with patch('toksec.api.urllib.request.build_opener', return_value=opener) as factory:
            client = Responses('test-key')
            payload = {'model': 'example', 'service_tier': 'default', 'input': 'hello'}
            self.assertEqual(client.post('responses', payload, 17), {'id': 'response-example'})
        factory.assert_called_once()
        self.assertIsInstance(factory.call_args.args[0], NoRedirect)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertEqual(json.loads(request.data), payload)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 17})

    def test_http_error_does_not_retry_or_disclose_response_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            'https://api.openai.com/v1/responses', 429, 'private diagnostic', {}, None)
        with patch('toksec.api.urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, '^API HTTP 429; no automatic retry$'):
                Responses('test-key').post('responses', {}, 10)
        opener.open.assert_called_once()

    def test_redirect_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'redirects are not allowed'):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid/')

    def test_missing_credentials_fail_before_transport_creation(self):
        with patch('toksec.api.urllib.request.build_opener') as factory:
            with self.assertRaisesRegex(ValueError, 'not configured'):
                Responses('')
        factory.assert_not_called()


class SharedMeteringTests(unittest.TestCase):
    def usage(self):
        return {'input_tokens': 100, 'output_tokens': 40, 'total_tokens': 140,
                'input_tokens_details': {'cached_tokens': 10, 'cache_write_tokens': 20},
                'output_tokens_details': {'reasoning_tokens': 10}}

    def test_usage_accounts_for_cache_and_reasoning_without_double_counting(self):
        record = metering.usage_record(self.usage())
        self.assertEqual(record, {'input': 100, 'cached_input': 10, 'cache_write': 20,
                                 'output': 40, 'reasoning': 10, 'total': 140,
                                 'cost_usd_upper_bound': '0.0000321'})

    def test_missing_cache_write_detail_uses_conservative_rate(self):
        usage = self.usage(); usage.pop('input_tokens_details')
        self.assertEqual(metering.usage_record(usage)['cost_usd_upper_bound'], '0.000045')

    def test_long_context_multiplier_is_preserved(self):
        usage = {'input_tokens': 400000, 'output_tokens': 100, 'total_tokens': 400100,
                 'input_tokens_details': {'cache_write_tokens': 0}}
        self.assertEqual(metering.usage_record(usage)['cost_usd_upper_bound'], '0.080075')

    def test_invalid_counts_and_subsets_are_rejected(self):
        for invalid in (-1, True, 1.0, '1'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                metering.tokens(invalid)
        usage = self.usage(); usage['total_tokens'] = 141
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            metering.usage_record(usage)
        usage = self.usage(); usage['output_tokens_details']['reasoning_tokens'] = 41
        with self.assertRaisesRegex(ValueError, 'subsets'):
            metering.usage_record(usage)

    def test_totals_include_pending_reservations(self):
        ledger = {'token_limit': 100, 'dollar_limit': '1', 'requests': [
            {'state': 'settled', 'usage': {'total': 3, 'cost_usd_upper_bound': '0.02'}},
            {'state': 'reserved', 'reserved_tokens': 11, 'reserved_usd': '0.03'}]}
        self.assertEqual(metering.totals(ledger), {'used': 3, 'reserved': 11, 'remaining': 86,
                                                 'spent_usd_upper_bound': '0.02',
                                                 'reserved_usd': '0.03', 'remaining_usd': '0.95'})
