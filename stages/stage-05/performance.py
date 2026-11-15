from dataclasses import replace
from toksec.stages import module as stage_module
base = stage_module(2, 'performance').workloads
from stages.common.performance import matrix

def workloads():
    selected = base()
    selected += [replace(w, host='beta.test') for w in matrix([('routed', True, False, False, '/assets/')])]
    selected += matrix([('proxy', True, False, False, '/proxy/data/')])
    selected += matrix([('cache-hit', True, False, False, '/proxy/cache/'), ('cache-miss', True, False, False, '/proxy/miss/')])
    return selected
