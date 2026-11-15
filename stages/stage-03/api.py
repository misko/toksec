from toksec.stages import module as stage_module
INHERITED = stage_module(2, 'api').CASES
from evaluation.api.routing import CASES as OWN
CASES = INHERITED + OWN
