from toksec.stages import module as stage_module
INHERITED = stage_module(4, 'api').CASES
from evaluation.api.operations import CASES as OWN
CASES = INHERITED + OWN
