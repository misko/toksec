from stages.common.grading.gateway_origin import control
from stages.common.grading.performance import matrix


def workloads_for(stage):
    if stage == 14:
        return matrix([('gateway-14-public', True, False, False, '/data/'),
                       ('gateway-14-admitted', True, False, False, '/gateway/data/')])
    prefix = '/gateway/data/'
    return matrix([(f'gateway-{stage}', True, False, False, prefix)])


def validate_effects(stage, measurement, before, after, public_route=False):
    counts = {key: after.get(key, 0) - before.get(key, 0) for key in ('auth', 'origin')}
    delivered = measurement['all_successes']
    if stage in (12, 13):
        origin_ok = (after.get('origin', 0) > 0 and counts['origin'] < delivered)
    elif public_route:
        origin_ok = counts['origin'] == 0
    else:
        origin_ok = counts['origin'] == delivered
    auth_ok = counts['auth'] == (delivered if stage in (11, 13) else 0)
    measurement.update(fixture_requests=counts, effects_verified=origin_ok and auth_ok)
    measurement['eligible'] &= measurement['effects_verified']
