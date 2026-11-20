import csv
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

from stages.common.grading.performance import Workload
from scripts import plot_releases


WORKLOAD = Workload('gateway-14-public-4096-256', 256, '/data/4096', 4096, rounds=2)


def measured():
    first = dict(eligible=True, failures=0, timeouts=0, p95_ms=2, p99_ms=5,
                 generator_saturated=False, upstream_saturated=False,
                 effects_verified=True, upstream_sample_valid=True, clients_started=256,
                 attempts=1001, successes=1001, completed_in_window=1000, valid_rps=333)
    return {'eligible': True, 'failures': 0, 'median_rps': 333, 'min_rps': 333,
            'max_rps': 333, 'worst_p99_ms': 5,
            'rounds': [first, {**first, 'p95_ms': 4}]}


def timeline():
    return {'stage': 14, 'started_unix': 10, 'ended_unix': 70, 'total_checks': 22,
            'workloads': [asdict(WORKLOAD)], 'terminal_capacity': {'spent_usd_upper_bound': '0.42',
                                                                  'reserved_usd': '0.20'},
            'releases': [{'tag': 'release/000001', 'elapsed_seconds': 30, 'passed': 22,
                          'capacity': {'spent_usd_upper_bound': '0.23'}, 'api_status': 'passed',
                          'benchmarks': {WORKLOAD.id: measured()}}]}


class ReleaseFiguresTest(unittest.TestCase):
    def test_known_workload_validates_failures_and_rounds(self):
        data = timeline()
        w = plot_releases.declared_workloads(data)
        summary = data['releases'][0]['benchmarks'][WORKLOAD.id]
        data['releases'][0]['api_status'] = 'not_run'
        self.assertEqual(plot_releases.observations(data, w)[1][0]['qualification'], 'Unavailable')
        data['releases'][0]['api_status'] = 'passed'
        row = plot_releases.observations(data, w)[1][0]
        self.assertEqual(row['median_p95_ms'], 3)
        self.assertEqual(row['median_rps'], 333)
        summary['failures'] = 1
        row = plot_releases.observations(data, w)[1][0]
        self.assertEqual(row['qualification'], 'Request failures')
        self.assertIsNone(row['median_rps'])
        self.assertEqual(row['failures'], 1)
        summary['rounds'][0]['generator_saturated'] = True
        row = plot_releases.observations(data, w)[1][0]
        self.assertEqual(row['qualification'], 'Failures and other issues')
        self.assertIn('generator_saturated', row['issues'])
        summary['failures'] = 0
        summary['rounds'] = summary['rounds'][1:]
        row = plot_releases.observations(data, w)[1][0]
        self.assertIsNone(row['median_p95_ms'])
        self.assertIn('incomplete_rounds', row['issues'])

    def test_release_retention_breaks_at_missing_tag(self):
        points = plot_releases.step_coordinates([1, 2, 3], [10, None, 20], 4)
        self.assertEqual(points[:2], [(1, 10), (2, 10)])
        self.assertTrue(all(math.isnan(n) for n in points[2]))
        self.assertEqual(points[3:], [(3, 20), (4, 20)])
        data = timeline()
        xs = plot_releases.axis_definitions(data)
        self.assertEqual((xs[0][1:], xs[1][1:]), (([.5], 1), ([.23], .42)))
        del data['terminal_capacity']
        del data['releases'][0]['capacity']
        self.assertEqual(plot_releases.axis_definitions(data)[1][1:], ([None], None))

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'), 'matplotlib required to render figures')
    def test_plot_exports_gated_data_and_separate_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            data = timeline()
            (path / 'timeline.json').write_text(json.dumps(data))
            out = path / 'parent-evaluation' / 'figures'
            plot_releases.plot(path, out)
            with (out / 'metrics.csv').open() as f:
                row, = list(csv.DictReader(f))
            self.assertEqual(row['qualification'], 'Qualified')
            self.assertEqual(row['settled_usd_upper_bound'], '0.23')
            self.assertEqual(row['median_p95_ms'], '3.0')
            self.assertTrue((out / 'performance.png').read_bytes().startswith(b'\x89PNG'))
            self.assertIn('Cumulative settled spend', (out / 'correctness.svg').read_text())


if __name__ == '__main__':
    unittest.main()
