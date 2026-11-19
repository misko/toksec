"""CPU-light correctness tests; no sockets, performance rounds, or model calls."""
import copy
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('supplemental', HERE / 'supplemental.py')
supplemental = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supplemental)
from toksec.wire import payload
from toksec.specification import workloads


class NativeResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='toksec-native-validator-')
        cls.worker = Path(cls.temporary.name) / 'native_load'
        supplemental.compile_worker(cls.worker)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def check(self, raw, passed, size=4096, chunk=65536, error=None):
        result = subprocess.run([str(self.worker), '--validate', str(chunk), '--size', str(size)],
                                input=raw, capture_output=True, timeout=5)
        self.assertEqual(result.returncode == 0, passed, result.stderr.decode())
        if passed:
            return json.loads(result.stdout)
        if error:
            self.assertIn(error, result.stderr.decode())

    @staticmethod
    def response(headers=b'', body=None, size=4096, status=b'HTTP/1.1 200 OK'):
        return status + b'\r\nContent-Length: ' + str(size).encode() + b'\r\n' + headers + b'\r\n' + (payload(size) if body is None else body)

    def test_exact_calibration_payloads_all_fragment_boundaries(self):
        # The unchanged calibration fixture uses toksec.wire.payload's byte pattern.
        for size in (4096, 65536):
            for chunk in (1, 2, 3, 7, 17, 64, 4096, 65536):
                with self.subTest(size=size, chunk=chunk):
                    result = self.check(self.response(size=size), True, size, chunk)
                    self.assertFalse(result['connection_close'])

    def test_connection_tokens(self):
        for header in (b'Connection: CLOSE\r\n', b'Connection: keep-alive, close\r\n'):
            self.assertTrue(self.check(self.response(header), True)['connection_close'])
        self.assertTrue(self.check(self.response(status=b'HTTP/1.0 200 OK'), True)['connection_close'])
        self.assertFalse(self.check(self.response(b'Connection: keep-alive\r\n', status=b'HTTP/1.0 200 OK'), True)['connection_close'])

    def test_bad_status(self):
        for status in (b'HTTP/1.1 201 OK', b'HTTP/1.1 2000 OK', b'HTTP/2.0 200 OK', b'HTTP/1.1 +200 OK', b'HTTP/1.1 200 OK\nBad'):
            with self.subTest(status=status):
                self.check(self.response(status=status), False, error='status')

    def test_framing_rejections(self):
        for headers in (b'Content-Length: 4096\r\n', b'content-length: 4096\r\n',
                        b'Transfer-Encoding: chunked\r\n', b'Transfer-Encoding: identity\r\n',
                        b'Content-Encoding: gzip\r\n', b' Bad: value\r\n', b'Bad : value\r\n',
                        b'Bad: value\x00\r\n', b'Bad: folded\r\n continuation\r\n'):
            with self.subTest(headers=headers):
                self.check(self.response(headers), False)
        for length in (b'-1', b'+4096', b'4096, 4096', b'', b'4095', b'4097', b'99999999999999999999999999999999999999999'):
            self.check(b'HTTP/1.1 200 OK\r\nContent-Length: ' + length + b'\r\n\r\n' + payload(4096), False)
        self.check(b'HTTP/1.1 200 OK\r\n\r\n' + payload(4096), False, error='content_length')

    def test_corruption_truncation_and_extra_bytes(self):
        body = bytearray(payload(4096)); body[2048] ^= 1
        self.check(self.response(body=bytes(body)), False, error='payload')
        self.check(self.response(body=payload(4096)[:-1]), False, error='truncated')
        self.check(self.response() + b'x', False, error='trailing_bytes')
        self.check(self.response() + self.response(), False, error='trailing_bytes')
        self.check(self.response() + b'x', False, chunk=1, error='trailing_bytes')
        self.check(b'HTTP/1.1 200 OK\r\nContent-Length: 4096\r\n', False, error='truncated')

    def test_oversize_header(self):
        self.check(self.response(b'X-Large: ' + b'x' * 65536 + b'\r\n'), False, error='header_too_large')

    def monitor(self, milliseconds):
        result = subprocess.run([str(self.worker), '--size', '4096', '--lag-probe',
                                 ','.join(str(int(ms * 1000000)) for ms in milliseconds)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_lag_ordinary_fixed_cadence(self):
        result = self.monitor(range(0, 4001, 10))
        self.assertEqual(result['lag_samples'], 300)
        self.assertEqual(result['expected_lag_samples'], 300)
        self.assertEqual(result['lag_max_ms'], 0)
        self.assertEqual(result['lag_over_20ms'], 0)
        self.assertEqual(result['lag_missed_deadlines'], 0)
        self.assertTrue(result['lag_coverage_valid'])

    def test_lag_multi_second_pause_resuming_after_measurement_end(self):
        result = self.monitor(list(range(0, 1501, 10)) + [4500])
        self.assertEqual(result['lag_samples'], 300)
        self.assertEqual(result['lag_max_ms'], 2990)
        self.assertEqual(result['lag_over_20ms'], 249)
        self.assertEqual(result['lag_missed_deadlines'], 249)
        self.assertEqual(result['legacy_lag_over_20ms'], 0)
        self.assertEqual(result['legacy_lag_samples'], 51)
        self.assertTrue(result['lag_coverage_valid'])
        # The v1 gate missed this pause. Fixed deadlines must reject the worker.
        part = GateAndEligibilityTests.worker(); part.update(result)
        outcome = GateAndEligibilityTests().aggregate(part)
        self.assertTrue(outcome['generator_saturated'])
        self.assertFalse(outcome['eligible'])

    def test_lag_pause_straddling_end_without_request_timeout(self):
        result = self.monitor(list(range(0, 3601, 10)) + [4250])
        self.assertEqual(result['lag_max_ms'], 640)
        self.assertEqual(result['lag_over_20ms'], 39)
        self.assertTrue(result['lag_coverage_valid'])
        part = GateAndEligibilityTests.worker(); part.update(result)
        self.assertFalse(GateAndEligibilityTests().aggregate(part)['eligible'])

    def test_lag_ignores_gaps_outside_measurement(self):
        result = self.monitor([0, 990] + list(range(1000, 4001, 10)) + [9000])
        self.assertEqual(result['lag_samples'], 300)
        self.assertEqual(result['lag_over_20ms'], 0)
        self.assertEqual(result['lag_max_ms'], 0)
        self.assertTrue(result['lag_coverage_valid'])

    def test_lag_missing_end_observation_has_invalid_coverage(self):
        result = self.monitor(range(0, 3001, 10))
        self.assertEqual(result['lag_samples'], 201)
        self.assertFalse(result['lag_coverage_valid'])
        part = GateAndEligibilityTests.worker(); part.update(result)
        self.assertFalse(GateAndEligibilityTests().aggregate(part)['eligible'])


class GateAndEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='toksec-native-gate-')
        self.root = Path(self.temporary.name)
        artifact = self.root / 'candidate'; artifact.mkdir()
        self.source = self.root / 'main.cpp'; self.source.write_text('// fixture\n')
        (artifact / 'main.cpp').write_bytes(self.source.read_bytes())
        (artifact / 'server').write_bytes(b'fixture')
        (artifact / 'build.json').write_text('{"passed":true}')
        self.record = {'level': 1, 'language': 'cpp', 'framework': supplemental.fingerprint(),
                       'source_sha256': supplemental.digest(self.source), 'build': {'passed': True},
                       'checks': {'passed': True, 'cases': [{'id': c.id, 'passed': True} for c in supplemental.cases_for(1) + supplemental.EXTERNAL_CASES]}}
        self.acceptance = self.root / 'result.json'

    def tearDown(self):
        self.temporary.cleanup()

    def check_gate(self, passed):
        self.acceptance.write_text(json.dumps(self.record))
        if passed: supplemental.accepted(self.acceptance, self.source)
        else:
            with self.assertRaises((ValueError, FileNotFoundError)):
                supplemental.accepted(self.acceptance, self.source)

    def test_full_acceptance(self):
        self.check_gate(True)

    def test_reject_missing_or_failed_cases(self):
        original = copy.deepcopy(self.record)
        self.record['checks']['cases'].pop(); self.check_gate(False)
        self.record = copy.deepcopy(original); self.record['checks']['cases'][0]['passed'] = False; self.check_gate(False)
        self.record = copy.deepcopy(original); self.record['checks']['cases'].append(self.record['checks']['cases'][0]); self.check_gate(False)

    def test_reject_stale_source_framework_smoke(self):
        original = copy.deepcopy(self.record)
        for key, value in (('source_sha256', 'bad'), ('framework', 'bad'), ('evaluation_scope', 'visible_smoke_only')):
            self.record = copy.deepcopy(original); self.record[key] = value; self.check_gate(False)
        self.record = original
        self.source.write_text('// changed\n'); self.check_gate(False)

    def test_reject_changed_artifact_source(self):
        (self.root / 'candidate/main.cpp').write_text('// other\n'); self.check_gate(False)

    @staticmethod
    def worker():
        histogram = [0] * supplemental.BINS; histogram[1] = 100
        return {'histogram': histogram, 'attempts': 100, 'successes': 100, 'completed_in_window': 100,
                'failures': 0, 'timeouts': 0, 'warmup_failures': 0, 'payload_bytes': 409600,
                'clients_started': 64, 'cpu_seconds': 1, 'measurement_cpu_seconds': .8,
                'measurement_cpu_utilization': .8 / 3, 'rss_kib': 1000, 'elapsed_seconds': 4,
                'lag_samples': 300, 'expected_lag_samples': 300, 'lag_coverage_valid': True,
                'lag_missed_deadlines': 0, 'lag_over_20ms': 0, 'lag_max_ms': 0,
                'legacy_lag_samples': 290, 'legacy_lag_over_20ms': 0, 'peak_inflight': 64}

    def aggregate(self, part, upstream=None):
        return supplemental.aggregate([copy.deepcopy(part) for _ in range(4)], asdict(workloads(1)[0]),
                                      {'child_processes': 0}, upstream, [10, 11, 12, 13, 14])

    def test_cpu_and_lag_thresholds_never_relaxed(self):
        part = self.worker(); self.assertTrue(self.aggregate(part)['eligible'])
        part['cpu_seconds'] = 3.61; self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['measurement_cpu_utilization'] = .9001; self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['lag_over_20ms'] = 4; self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['lag_samples'] = 0; self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['lag_over_20ms'] = 3; self.assertTrue(self.aggregate(part)['eligible'])
        part['legacy_lag_over_20ms'] = 3
        self.assertFalse(self.aggregate(part)['eligible'])  # Never relax v1's denominator.
        part = self.worker(); part['lag_coverage_valid'] = False; self.assertFalse(self.aggregate(part)['eligible'])

    def test_upstream_and_error_eligibility(self):
        part = self.worker()
        self.assertFalse(self.aggregate(part, {'sample_valid': True, 'utilization': .91})['eligible'])
        self.assertFalse(self.aggregate(part, {'sample_valid': False, 'utilization': 0})['eligible'])
        part['failures'] = 1; part['attempts'] += 1
        self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['warmup_failures'] = 1
        self.assertFalse(self.aggregate(part)['eligible'])
        part = self.worker(); part['attempts'] += 1
        self.assertFalse(self.aggregate(part)['accounting_valid'])


class UpstreamGuardTests(unittest.TestCase):
    def test_running_upstream_is_allowed(self):
        upstream = Mock()
        upstream.poll.return_value = None
        supplemental.require_upstream_alive(upstream)
        upstream.poll.assert_called_once_with()

    def test_exited_upstream_is_rejected_even_when_proc_entry_exists(self):
        for code in (0, 7, -9):
            with self.subTest(returncode=code), patch.object(Path, 'exists', return_value=True):
                upstream = Mock()
                upstream.poll.return_value = code
                with self.assertRaisesRegex(RuntimeError, f'exited with code {code}'):
                    supplemental.require_upstream_alive(upstream)

    def test_static_workload_needs_no_upstream(self):
        supplemental.require_upstream_alive(None)

    def run_with_exit(self, poll_results, worker_running):
        upstream = Mock(pid=12345)
        upstream.poll.side_effect = poll_results
        workers = [Mock(returncode=0) for _ in range(4)]
        for worker in workers: worker.poll.return_value = None if worker_running else 0
        with tempfile.TemporaryDirectory(prefix='toksec-upstream-guard-') as temporary:
            with patch.object(supplemental.subprocess, 'Popen', side_effect=workers) as spawn, \
                    patch.object(supplemental, 'proc_sample', return_value=(0, 0, 0)):
                with self.assertRaisesRegex(RuntimeError, 'trusted upstream exited with code 7'):
                    supplemental.run_round(asdict(workloads(1)[0]), Path('/unused/worker'),
                                           {'server_pid': 56789}, [10, 11, 12, 13, 14, 15], Path(temporary), upstream)
        return spawn, workers

    def test_exit_before_round_prevents_worker_launch(self):
        spawn, _ = self.run_with_exit([7], False)
        spawn.assert_not_called()

    def test_exit_during_round_stops_workers(self):
        spawn, workers = self.run_with_exit([None, 7], True)
        self.assertEqual(spawn.call_count, 4)
        for worker in workers:
            worker.kill.assert_called_once_with()
            worker.wait.assert_called_once_with()

    def test_exit_after_workers_finish_prevents_result(self):
        spawn, workers = self.run_with_exit([None, 7], False)
        self.assertEqual(spawn.call_count, 4)
        for worker in workers:
            worker.kill.assert_not_called()
            worker.wait.assert_called_once_with()

    def test_exit_during_result_aggregation_prevents_return(self):
        upstream = Mock(pid=12345)
        upstream.poll.side_effect = [None, None, None, 7]
        def worker_process(*args, **kwargs):
            kwargs['stdout'].write('{}')
            worker = Mock(returncode=0)
            worker.poll.return_value = 0
            return worker
        with tempfile.TemporaryDirectory(prefix='toksec-upstream-guard-') as temporary:
            with patch.object(supplemental.subprocess, 'Popen', side_effect=worker_process), \
                    patch.object(supplemental, 'proc_sample', return_value=(0, 0, 0)), \
                    patch.object(Path, 'exists', return_value=True), \
                    patch.object(supplemental, 'aggregate', return_value={'eligible': True, 'ineligible_reasons': []}) as aggregate:
                with self.assertRaisesRegex(RuntimeError, 'trusted upstream exited with code 7'):
                    supplemental.run_round(asdict(workloads(1)[0]), Path('/unused/worker'),
                                           {'server_pid': 56789}, [10, 11, 12, 13, 14, 15], Path(temporary), upstream)
                aggregate.assert_called_once()

    def test_successful_proxy_round_retains_process_and_numeric_metrics(self):
        upstream = Mock(pid=12345)
        upstream.poll.return_value = None
        part = GateAndEligibilityTests.worker()
        spawned = []
        def worker_process(*args, **kwargs):
            json.dump(part, kwargs['stdout'])
            worker = Mock(returncode=0)
            worker.poll.return_value = 0
            if not spawned:
                worker.poll.side_effect = [None, None, None, 0, 0]
            spawned.append(worker)
            return worker
        with tempfile.TemporaryDirectory(prefix='toksec-upstream-round-') as temporary:
            with patch.object(supplemental.subprocess, 'Popen', side_effect=worker_process), \
                    patch.object(supplemental, 'proc_sample', return_value=(1, 100, 0)), \
                    patch.object(supplemental.time, 'monotonic_ns', return_value=0), \
                    patch.object(supplemental.time, 'monotonic', side_effect=[2.0, 3.5, 4.99]), \
                    patch.object(supplemental.time, 'sleep'), \
                    patch.object(Path, 'exists', return_value=True):
                spec = next(w for w in workloads(4) if w.id == 'proxy-4096-256')
                result = supplemental.run_round(asdict(spec), Path('/unused/worker'),
                                                {'server_pid': 56789}, [10, 11, 12, 13, 14, 15], Path(temporary), upstream)
        self.assertGreaterEqual(upstream.poll.call_count, 4)
        self.assertEqual(result['upstream']['pid'], 12345)
        self.assertEqual(result['upstream']['cpu_seconds'], 0)
        self.assertEqual(result['upstream']['peak_rss_kib'], 100)
        self.assertEqual(result['attempts'], 400)
        self.assertEqual(result['successes'], 400)
        self.assertEqual(result['failures'], 0)
        self.assertEqual(result['valid_rps'], 400 / 3)
        self.assertEqual(result['payload_bytes'], 400 * 4096)
        self.assertEqual(result['p99_ms'], .1)
        self.assertTrue(result['accounting_valid'])
        self.assertTrue(result['upstream']['sample_valid'])
        self.assertTrue(result['server']['sample_valid'])
        self.assertTrue(result['eligible'])

    def test_fixture_stdout_stderr_are_retained(self):
        upstream = Mock(pid=12345)
        upstream.poll.return_value = None
        def fixture_process(*args, **kwargs):
            kwargs['stdout'].write(b'fixture startup\n')
            kwargs['stderr'].write(b'fixture diagnostic\n')
            return upstream
        with tempfile.TemporaryDirectory(prefix='toksec-upstream-logs-') as temporary:
            root = Path(temporary)
            (root / 'supplemental-upstream.ready').write_text('ready')
            config = {'cpus': [10, 11, 12, 13, 14, 15], 'runtime': {'fixtures': str(root), 'server_pid': 56789},
                      'output': str(root), 'level': 4, 'workloads': [], 'rounds': 1, 'worker': '/unused/worker'}
            with patch.object(supplemental.subprocess, 'Popen', side_effect=fixture_process), \
                    patch.object(supplemental.socket, 'create_connection', return_value=MagicMock()), \
                    patch.object(supplemental.os, 'sched_getaffinity', side_effect=[{10}, {15}]):
                supplemental.inside(config)
            self.assertEqual((root / 'upstream.stdout.log').read_text(), 'fixture startup\n')
            self.assertEqual((root / 'upstream.stderr.log').read_text(), 'fixture diagnostic\n')
            upstream.terminate.assert_called_once_with()
            upstream.wait.assert_called_once_with(timeout=3)


if __name__ == '__main__':
    unittest.main()
