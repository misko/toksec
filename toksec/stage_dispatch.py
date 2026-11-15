"""Select a runtime from the frozen run identity and serialize CLI mutations."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path

SUPPORTED_STAGES = (1, 2, 3, 4, 5, 10)


def stage_of(run):
    manifest = json.loads((Path(run) / 'manifest.json').read_text())
    stage = manifest.get('stage', manifest.get('level'))
    if type(stage) is not int or stage not in SUPPORTED_STAGES:
        raise ValueError('unsupported stage identity')
    if 'level' in manifest and manifest['level'] != stage:
        raise ValueError('conflicting stage identities')
    return stage


@contextmanager
def operation_lock(run):
    from toksec import campaign
    manifest = json.loads((Path(run) / 'manifest.json').read_text())
    if manifest.get('campaign'):
        with campaign.locked(manifest['campaign'], owner=True):
            yield
    else:
        if stage_of(run) != 10:
            raise ValueError('campaign identity is missing')
        with (Path(run) / 'run.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def stage10_tool(run, name, arguments):
    from stage10 import runner
    manifest = runner.read(run, 'manifest.json')
    if manifest['framework'] != runner.identity():
        raise ValueError('framework changed since preparation; prepare a fresh run')
    return runner.dispatch(run, name, arguments)


def stage10_benchmark(run, workload=None):
    choices = {f'{protocol}-{clients}': {'tls': protocol == 'https', 'clients': clients}
               for protocol in ('http', 'https') for clients in (256, 4096)}
    if workload is not None and workload not in choices:
        raise ValueError('Stage 10 diagnostic workload must be http-256, http-4096, https-256, or https-4096')
    selected = choices if workload is None else {workload: choices[workload]}
    return {'coverage': 'partial', 'scope': 'provisional', 'final_grade_eligible': False,
            'benchmarks': {name: stage10_tool(run, 'benchmark_candidate', args)
                           for name, args in selected.items()}}


def stage10_revalidate(run, target):
    from stage10 import runner
    if target not in ('latest', 'incumbent'):
        raise ValueError('target must be incumbent or latest')
    manifest, state = runner.read(run, 'manifest.json'), runner.read(run)
    candidate = state['tags'][-1]['candidate'] if target == 'incumbent' and state['tags'] else state['latest']
    if not candidate:
        raise ValueError('no candidate to revalidate')
    filename = 'main.cpp' if manifest['language'] == 'cpp' else 'main.rs'
    source = (Path(run) / 'candidates' / candidate / filename).read_text()
    return stage10_tool(run, 'submit_candidate', {'source': source})
