import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from test_campaign import PARTIAL
from toksec import benchmark, sandbox
from toksec.wire import payload


class BenchmarkTests(unittest.TestCase):
    def test_exact_payload_required_and_framing_errors_rejected(self):
        async def check(raw, expected, reject):
            reader = asyncio.StreamReader()
            reader.feed_data(raw)
            reader.feed_eof()
            if reject:
                with self.assertRaises((ValueError, KeyError, asyncio.IncompleteReadError)):
                    await benchmark.response(reader, expected, False)
            else:
                self.assertTrue(await benchmark.response(reader, expected, False))
        asyncio.run(check(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\nabc', b'abc', False))
        for raw in (b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nxyz',
                    b'HTTP/1.1 503 Error\r\nContent-Length: 3\r\n\r\nabc',
                    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nabc',
                    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\na'):
            asyncio.run(check(raw, b'abc', True))

    def test_real_driver_starts_256_and_4096_clients_and_accounts_every_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / 'candidate'
            self.assertTrue(sandbox.build(PARTIAL, artifact, 1)['passed'])
            for clients in (256, 4096):
                name = f'fresh-4096-{clients}'
                report = sandbox.invoke_driver(artifact, 1, 'benchmark', workload=name, rounds=1)[name]
                measured = report['rounds'][0]
                self.assertEqual(measured['clients_started'], clients)
                self.assertGreater(measured['successes'], 0)
                self.assertEqual(measured['attempts'], measured['successes'] + measured['failures'])
                self.assertEqual(measured['payload_bytes'], measured['completed_in_window'] * 4096)
                self.assertLessEqual(measured['timeouts'], measured['failures'])
                self.assertGreater(measured['server_peak_rss_kib'], 0)

    def test_failed_responses_do_not_count_as_goodput(self):
        from test_system import FIXTURE
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / 'candidate'
            self.assertTrue(sandbox.build(FIXTURE, artifact, 1)['passed'])
            measured = sandbox.invoke_driver(artifact, 1, 'benchmark', workload='fresh-4096-256', rounds=1)['fresh-4096-256']['rounds'][0]
            self.assertGreater(measured['failures'], 0)
            self.assertEqual(measured['valid_rps'], 0)
            self.assertIsNone(measured['p99_ms'])
