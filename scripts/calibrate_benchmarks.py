#!/usr/bin/env python3
"""Host-only calibration. No model calls; this does not grade an implementation."""
import argparse
import json
import hashlib
import platform
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.storage import atomic_json
from toksec.provenance import checkout
from toksec.calibrations import identity, index
from toksec import sandbox
from toksec.specification import ROOT, fingerprint, workloads


def calibrate(output=None, rounds=1):
    provenance = checkout()
    calibration_id = identity(provenance['toksec_commit'])
    output = Path(output or ROOT/'calibrations'/calibration_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifact = output/'probe'
    source = ROOT/'evaluation/performance/fixtures/load_reference.cpp'
    result = {**provenance, 'calibration_id': calibration_id, 'probe_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'environment': {'platform': platform.platform(), 'cpu_affinity': sorted(os.sched_getaffinity(0))},
              'framework': fingerprint(), 'purpose': 'Static generator calibration; not stage API conformance or proxy calibration',
              'build': sandbox.build(source.read_text(), artifact, 2, language='cpp'), 'benchmarks': {}}
    if not result['build']['passed']:
        raise RuntimeError(result['build']['diagnostics'])
    for workload in workloads(2):
        result['benchmarks'].update(sandbox.invoke_driver(artifact,2,'benchmark',workload=workload.id,rounds=rounds))
        atomic_json(output/'calibration.json', result)
    result['static_generator_ready'] = all(value['eligible'] and not value['failures'] for value in result['benchmarks'].values())
    result['proxy_calibration_ready'] = False
    result['launch_ready'] = False  # Static probe cannot certify proxy/operations attribution.
    result['next_step'] = ('Validate upstream headroom with a conforming proxy reference.' if result['static_generator_ready']
                           else 'Resolve load-generator saturation/failures before performance-comparison campaigns.')
    atomic_json(output/'calibration.json', result)
    (output/'report.md').write_text('# Static HTTP calibration\n\nSee calibration.json for workload measurements and eligibility.\nThis does not certify proxy workloads or agent implementations.\n')
    if output.parent == ROOT/'calibrations':
        index(output.parent)
    return result

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional output directory; defaults to calibrations/<calibration-id>')
    parser.add_argument('--rounds', type=int, choices=range(1,6), default=1)
    args=parser.parse_args()
    result=calibrate(args.output,args.rounds)
    print(json.dumps({k:v for k,v in result.items() if k != 'benchmarks'},indent=2))
