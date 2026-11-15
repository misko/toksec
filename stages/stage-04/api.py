from toksec.stages import module as stage_module
INHERITED = stage_module(3, 'api').CASES
from evaluation.api.proxy import CASES as OWN
CASES = INHERITED + OWN
