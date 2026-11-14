"""Standalone compile, public conformance and optional performance measurement."""
import json
from pathlib import Path
from controller import atomic_json
from toksec import sandbox
from toksec.specification import workloads


def evaluate(source, directory, level, performance=False):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=False)
    artifact=directory/'candidate'
    result={'level':level,'build':sandbox.build(Path(source).read_text(),artifact,level)}
    if result['build']['passed']:
        result['checks']=sandbox.evaluate(artifact,level)
        atomic_json(directory/'result.json',result)
        if performance and result['checks']['passed']:
            result['benchmarks']={}
            for workload in workloads(level):
                result['benchmarks'].update(sandbox.invoke_driver(artifact,level,'benchmark',workload=workload.id,rounds=workload.rounds))
                atomic_json(directory/'result.json',result)
        elif performance:
            result['benchmark_skipped']='Correctness checks must pass before performance measurement.'
    atomic_json(directory/'result.json',result)
    return result
