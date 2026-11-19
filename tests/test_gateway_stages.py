import unittest
from unittest.mock import patch

from stages.common.grading.gateway_checks import revocation
from stages.common.grading.gateway_load import validate_effects
from toksec.batch import plan
from toksec.specification import configuration, packet, specification
from toksec.stages import GATEWAY_STAGES
from toksec.wire import Response


class RevocationFixture:
    """Small decision/cache model; either optimization can be independently broken."""
    def __init__(self, skip_auth=False, bypass_cache=False):
        self.skip_auth = skip_auth
        self.bypass_cache = bypass_cache
        self.auth = self.origin = 0
        self.policy = {'reader': 200, 'other': 200}

    def snapshot(self, **policy):
        self.policy.update(policy)
        return {'auth': self.auth, 'origin': self.origin}

    def get(self, path, headers, status=200, body=None):
        token = headers['Authorization'].split()[1]
        self.auth += 1
        decision = 200 if self.skip_auth and self.origin else self.policy[token]
        assert decision == status
        if decision == 200 and (not self.origin or self.bypass_cache):
            self.origin += 1
        return Response(status, {}, b'document')


class GatewayTests(unittest.TestCase):
    def test_revocation_oracle_distinguishes_both_shortcuts(self):
        with patch('stages.common.grading.gateway_checks.snapshot', lambda c, **kw: c.snapshot(**kw)):
            revocation(RevocationFixture())
            for options in [{'skip_auth':True}, {'bypass_cache':True}]:
                with self.assertRaises(AssertionError):
                    revocation(RevocationFixture(**options))

    def test_effects_gate(self):
        for after,valid in [({'origin':1,'auth':10}, True), ({'origin':10,'auth':10}, False),
                            ({'origin':1,'auth':1}, False)]:
            r = {'eligible':True,'all_successes':10}
            validate_effects(13,r,{},after)
            self.assertEqual(r['eligible'],valid)

    def test_launch_order_and_public_contract(self):
        batch = plan(GATEWAY_STAGES,3,1,3,7200,'cpp',range(6))
        self.assertEqual([j['stage'] for j in batch['jobs']], list(GATEWAY_STAGES)*3)
        self.assertEqual(batch['total_cap_usd'],'54')
        for n in GATEWAY_STAGES:
            spec = specification(n,'cpp')
            self.assertEqual({w['clients'] for w in spec['benchmarks']},{256,4096})
            self.assertNotIn('proxy_prefix',configuration(n))
            self.assertNotIn('gateway_checks.py',packet(n,'cpp'))
            self.assertEqual('OpenSSL' in spec['build']['approved_libraries'], n==15)
