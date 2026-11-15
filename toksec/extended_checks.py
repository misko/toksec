"""Combined higher-stage cases for callers that need the capability catalog."""
from toksec.stages import module as stage_module

ROUTING = stage_module(3, 'api').OWN
PROXY = stage_module(4, 'api').OWN
OPERATIONS = stage_module(5, 'api').OWN
CASES = ROUTING + PROXY + OPERATIONS
