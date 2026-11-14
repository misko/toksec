from dataclasses import replace
from stages.stage2.performance import workloads as base
from stages.common.performance import matrix

def workloads():
    selected = base()
    selected += [replace(w, host='beta.test') for w in matrix([('routed', True, False, False, '/assets/')])]
    selected += matrix([('proxy', True, False, False, '/proxy/data/')])
    return selected
