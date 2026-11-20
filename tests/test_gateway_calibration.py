import unittest
from toksec.gateway_calibration import assess, environment, measurement_fingerprint
from toksec.specification import workloads


class GatewayCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.w = next(w for w in workloads(14) if w.id == 'gateway-14-admitted-4096-256')

    def raw(self):
        def row(rate):
            return {'clients_started': self.w.clients, 'attempts': 30, 'successes': 30, 'failures': 0, 'timeouts': 0,
                    'completed_in_window': 30, 'valid_rps': rate, 'p99_ms': 10.0, 'effects_verified': True,
                    'upstream_sample_valid': True, 'eligible': True, 'upstream_saturated': False, 'generator_saturated': False}
        r = {name: [row(rate) for i in range(5)] for name, rate in [('reference',100),('repeat',99),('slow_control',50)]}
        r.update(generator=[row(200)], origin=[row(175)])
        return r

    def test_direct_saturation_records_a_ceiling_but_cannot_hide_errors(self):
        raw = self.raw()
        raw['generator'][0].update(eligible=False, generator_saturated=True)
        self.assertTrue(assess(self.w, raw)['qualified'])
        raw['origin'][0].update(failures=1, successes=29, completed_in_window=29)
        self.assertIn('origin:request_failures', assess(self.w, raw)['reasons'])

    def test_incomplete_noisy_or_slow_control_never_qualifies(self):
        for name, rate, reason in [('repeat', 70, 'reference_repeat_variation'),
                                  ('slow_control', 99, 'known_slow_control_indistinguishable'),
                                  ('origin', 101, 'origin:insufficient_headroom')]:
            with self.subTest(name=name):
                raw = self.raw()
                for row in raw[name]:
                    row['valid_rps'] = rate
                self.assertIn(reason, assess(self.w, raw)['reasons'])
        raw = self.raw()
        raw['reference'].pop()
        self.assertFalse(assess(self.w, raw)['qualified'])

    def test_identity_separates_stage_and_records_host(self):
        self.assertNotEqual(measurement_fingerprint(14),measurement_fingerprint(16))
        self.assertTrue(environment()['cpu_affinity'])
