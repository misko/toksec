from toksec.stages import identifier as stage_id
"""One host catalog: stable IDs, contract references and explicit visibility."""
from dataclasses import asdict

def catalog(level):
    from toksec.checks import cases_for, configured_cases, EXTERNAL_CASES
    from evaluation.smoke.api import cases as smoke_cases
    result = []
    for check in cases_for(level) + configured_cases(level) + EXTERNAL_CASES:
        if check.id == 'configuration':
            contract = 'stages/common/INTERFACE.md'
        elif check.minimum >= 3:
            contract = 'stages/capabilities/' + {3:'routing',4:'proxy',5:'operations'}[check.minimum] + '.md'
        else:
            contract = 'stages/common/HTTP.md' if check.minimum == 1 else 'stages/stage-02/SPEC.md'
        result.append({'id': check.id, 'description': check.description, 'minimum': check.minimum,
                       'visibility': 'host_only', 'contract': contract})
    for check in smoke_cases(level):
        result.append({'id': check.id, 'description': check.description, 'minimum': check.minimum,
                       'visibility': 'visible_smoke', 'contract': f'stages/{stage_id(level)}/SPEC.md'})
    return result
