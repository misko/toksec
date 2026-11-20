import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toksec import calibrations, campaign, controller, gateway_calibration, runner
from toksec.specification import packet, specification
from toksec.storage import atomic_json


class DevelopmentCalibrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workloads = specification(14, 'cpp')['benchmarks']
        self.name = 'gateway-14-admitted-4096-256'
        selected = next(w for w in self.workloads if w['id'] == self.name)
        self.record = {
            'stage': 14, 'status': 'completed', 'calibration_id': 'private-receipt-id',
            'environment': gateway_calibration.environment(),
            'measurement_fingerprint': gateway_calibration.measurement_fingerprint(14),
            'control_description': 'host-only-control-marker', 'confirmatory_workload': 'host-only-holdback',
            'diagnostic_workload': self.name, 'declared_rounds': selected['rounds'], 'diagnostic_ready': True,
            'confirmation_ready': False, 'full_matrix_ready': False, 'workloads': {self.name: selected},
            'cells': {self.name: {'qualified': True, 'reasons': [], 'details': 'host-only-control-result'}}}
        self.receipt = self.root / 'private-receipt.json'
        atomic_json(self.receipt, self.record)

    def test_prepare_freezes_receipt_exposes_only_workload_and_checks_packet_on_resume(self):
        campaign.initialize(self.root / 'campaign', '3', request_profile='bounded-32k')

        def prepare(**options):
            return Path(controller.prepare(self.root / 'campaign', 14, language='cpp',
                                            model=campaign.TERRA, **options)['run'])

        default = prepare()
        run = prepare(development_calibration=self.receipt)
        manifest = controller.read(run, 'manifest.json')
        baseline = controller.read_launch_packet(default, controller.read(default, 'manifest.json'))
        self.assertEqual(baseline, packet(14, 'cpp'))
        self.assertEqual(controller.read_launch_packet(run, manifest), baseline +
                         f'\nFor a development comparison, try benchmark_candidate with workload `{self.name}`.\n')
        self.assertEqual(manifest['input_sha256'], controller.read(default, 'manifest.json')['input_sha256'])
        self.assertNotIn('development_calibration', controller.read(default, 'manifest.json'))
        self.assertEqual(manifest['development_calibration'], {
            'id': self.record['calibration_id'], 'sha256': hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
            'workload': self.name, 'measurement_fingerprint': self.record['measurement_fingerprint'],
            'environment_sha256': calibrations.environment_digest(self.record['environment'])})
        self.assertEqual(manifest['launch_packet_sha256'], hashlib.sha256((run / 'launch-packet.md').read_bytes()).hexdigest())
        self.receipt.unlink()
        with patch.object(gateway_calibration, 'environment', return_value={}):
            self.assertTrue(any('calibration environment' in why for why in runner.preflight(run)['reasons']))
        (run / 'launch-packet.md').write_text(baseline)
        for resume in (False, True):
            check = runner.preflight(run, resumed=resume)
            self.assertFalse(check['launch_allowed'])
            self.assertIn('launch packet differs from the prepared manifest', check['reasons'])

    def test_receipt_must_match_stage_host_workload_and_qualified_diagnostic(self):
        cases = ({'stage': 16}, {'environment': {}}, {'measurement_fingerprint': 'stale'},
                 {'status': 'running'}, {'diagnostic_ready': False}, {'diagnostic_workload': 'undeclared'},
                 {'declared_rounds': 1}, {'cells': {self.name: {'qualified': False, 'reasons': []}}},
                 {'cells': {self.name: {'qualified': True, 'reasons': ['saturated']}}},
                 {'workloads': {self.name: {**self.record['workloads'][self.name], 'clients': 1}}})
        for change in cases:
            with self.subTest(change=change):
                atomic_json(self.receipt, {**self.record, **change})
                with self.assertRaises(ValueError):
                    calibrations.development_hint(self.receipt, 14, self.workloads)
