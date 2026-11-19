from toksec.stages import module
from stages.common.grading.gateway_checks import policy_cases

CASES = [*module(2, "api").CASES, *policy_cases(13)]
