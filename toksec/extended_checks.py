"""Compatibility import; authoritative cases live in evaluation.api."""
from evaluation.api.routing import CASES as ROUTING
from evaluation.api.proxy import CASES as PROXY
from evaluation.api.operations import CASES as OPERATIONS
CASES = ROUTING + PROXY + OPERATIONS
