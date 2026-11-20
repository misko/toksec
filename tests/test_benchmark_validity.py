import asyncio
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec import benchmark, controller, evaluate
from toksec.evaluation_artifacts import write_evaluation
from toksec.specification import workloads
from toksec.storage import atomic_json


def measured_round(workload, speed=100, **changes):
    return dict({'eligible': True, 'effects_verified': True, 'attempts': 100, 'successes': 100,
                 'completed_in_window': 100, 'clients_started': workload.clients,
                 'failures': 0, 'timeouts': 0, 'valid_rps': speed, 'p99_ms': 1,
                 'upstream_sample_valid': True, 'upstream_saturated': False,
                 'generator_saturated': False}, **changes)


def measured_cell(workload, **changes):
    return benchmark.summarize([measured_round(workload, **changes) for _ in range(workload.rounds)], workload)


class ValidityTests(unittest.TestCase):
    def test_ineligible_cells_keep_both_failure_and_environment_causes(self):
        w = workloads(14)[0]
        bad = measured_cell(w, eligible=False, effects_verified=False, generator_saturated=True,
                            upstream_saturated=True, successes=98, completed_in_window=98, failures=2, timeouts=1,
                            failure_classes={'timeout_response': 1, 'http_503': 1})
        self.assertEqual(bad['validity_reasons'],
                         ['effects_unverified', 'generator_saturated', 'request_failures', 'timeouts', 'upstream_saturated'])
        self.assertEqual(bad['failure_classes'], {'http_503': w.rounds, 'timeout_response': w.rounds})
        self.assertFalse(benchmark.cell_valid(bad, w))
        failed = measured_cell(w, successes=99, completed_in_window=99, failures=1)
        self.assertTrue(failed['eligible'])
        self.assertEqual(benchmark.cell_issues(failed, w), ['request_failures'])

    def test_missing_workloads_rounds_clients_and_calibration_prevent_a_score(self):
        expected = workloads(14)
        matrix = {w.id: measured_cell(w) for w in expected}
        self.assertTrue(benchmark.matrix_valid(matrix, expected))
        first = expected[0]
        self.assertFalse(benchmark.matrix_valid({first.id: matrix[first.id]}, expected))
        self.assertFalse(benchmark.cell_valid(measured_cell(replace(first, rounds=1)), first))
        self.assertEqual(benchmark.cell_issues(measured_cell(first, clients_started=1), first), ['client_count'])
        self.assertEqual(benchmark.cell_issues(measured_cell(first, effects_verified=None), first), ['effects_unverified'])
        self.assertEqual(benchmark.cell_issues({**matrix[first.id], 'calibration_qualified': False}, first),
                         ['calibration_unqualified'])
        self.assertEqual(benchmark.cell_issues({**matrix[first.id], 'median_rps': 250}, first), ['mismatched_summary'])

    def test_grader_cli_and_envelope_agree_on_partial_or_failed_cell(self):
        expected = workloads(14)
        matrix = {w.id: measured_cell(w) for w in expected}
        result = {'stage': 14, 'checks': {'passed': True, 'cases': [{'id': 'api', 'passed': True}]}}
        for measurements, code, status in (
            (matrix, 0, 'measured'),
            ({}, 3, 'invalid_measurement'),
            ({w.id: matrix[w.id] for w in expected[:1]}, 3, 'invalid_measurement'),
            ({**matrix, expected[0].id: measured_cell(expected[0], failures=1)}, 3, 'invalid_measurement'),
        ):
            result['benchmarks'] = measurements
            self.assertEqual(evaluate.exit_code(result, True), code)
            with tempfile.TemporaryDirectory() as output:
                envelope = write_evaluation(output, run_id='example', release={'tag': 'release/000001',
                    'commit': 'a' * 40, 'source_sha256': 'b' * 64}, contract_sha256='c' * 64,
                    evaluator_sha256='d' * 64, environment={}, coverage='full', result=result)
                self.assertEqual(envelope['performance']['status'], status)

    def test_diagnostic_references_follow_qualified_source_without_changing_final_release(self):
        work = workloads(14)[0]
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            state = {'best': 'first', 'last': 'second', 'finished': False, 'optimization_attempts': 0}
            atomic_json(run / 'state.json', state)
            for name in ('first', 'second', 'third'):
                (run / 'candidates' / name).mkdir(parents=True)
                atomic_json(run / 'candidates' / name / 'report.json', {'checks': {'passed': True}})
            def drive(candidate, stage, mode, *, workload, rounds):
                row = measured_round(work, generator_saturated=candidate.name == 'first',
                                     eligible=candidate.name != 'first', speed=110 if candidate.name == 'third' else 100)
                return {workload: {'rounds': [row]}}
            with patch.object(controller, 'stage_of', return_value=14), patch.object(controller, 'validate', return_value={'stage': 14}), \
                    patch.object(controller, 'capacity', return_value={'seconds_remaining': 7200}), \
                    patch.object(controller.sandbox, 'invoke_driver', side_effect=drive), patch.object(controller, 'export'):
                result = controller.measure(run, work.id)
                self.assertEqual(result['decision']['reason'], 'first qualified comparison baseline')
                self.assertFalse(result['decision']['promote'])
                self.assertEqual(result['decision']['diagnostic_baseline'], 'second')
                state = json.loads((run / 'state.json').read_text())
                state['last'] = 'third'
                atomic_json(run / 'state.json', state)
                result = controller.measure(run, work.id)
                self.assertEqual(result['incumbent'], 'second')
                self.assertEqual(result['decision']['diagnostic_baseline'], 'third')
                self.assertAlmostEqual(result['decision']['geometric_gain'], 1.1)
                self.assertEqual(controller.read(run)['best'], 'first')

    def test_response_validation_keeps_specific_error_causes(self):
        async def fail(wire):
            reader = asyncio.StreamReader()
            reader.feed_data(wire)
            reader.feed_eof()
            await benchmark.response(reader, b'hello', False)
        with self.assertRaisesRegex(benchmark.ResponseFailure, 'http_502'):
            asyncio.run(fail(b'HTTP/1.1 502 Error\r\n\r\n'))
        with self.assertRaisesRegex(benchmark.ResponseFailure, 'body_mismatch'):
            asyncio.run(fail(b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nother'))
