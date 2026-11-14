import hashlib
import json
from dataclasses import asdict
from stages.common.performance import Workload, matrix
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'http-v8'
TITLES = {1: 'Static files', 2: 'Concurrent persistent HTTP', 3: 'Hosts and routing',
          4: 'Reverse proxy', 5: 'Plaintext operations'}
DESIGN = {
    1: 'Begin with a blocking, bounded request reader and exact file response. Submit that runnable path early. Add strict parsing and confinement before optimizing. Consider bounded workers or nonblocking sockets only after the contract passes. Avoid allocating the whole file per connection; immutable file metadata and sendfile are permitted.',
    2: 'Model each connection with explicit read-header, write-header, write-body and idle states. At 4096 clients a thread and a large buffer per connection can exceed the memory limit. Consider nonblocking sockets with epoll/poll and small bounded buffers. Track deadlines independently and preserve pipeline order under partial writes.',
    3: 'Normalize and validate the path once, then select host and route before opening a confined file. Keep conditional requests, ranges and HEAD as transformations of one representation descriptor. Avoid divergent GET/HEAD paths and validate alias confinement separately.',
    4: 'Model downstream and upstream lifecycles separately. Bound request and response bodies, make retry eligibility explicit, and return failed connections to no pool. First prove byte-exact proxying, then add healthy connection reuse and nonblocking backpressure.',
    5: 'Treat configuration as an immutable snapshot replaced after validation. Bound cache bytes and test shutdown before optimizing.',
}
BASE_CONFIG = {'listen': '127.0.0.1:8080', 'root': '/www', 'max_connections': '8192',
               'header_bytes': '8192', 'header_timeout_ms': '1000', 'idle_timeout_ms': '2000',
               'write_timeout_ms': '2000', 'max_requests': '100', 'pipeline_depth': '16'}
EXTRA_CONFIG = {
    3: {'default_host': 'alpha.test', 'host_root': 'beta.test:/www/beta',
        'alias': '/assets/:/www/assets/', 'redirect': '/old:/hello.txt', 'index': 'index.html'},
    4: {'proxy_prefix': '/proxy/', 'upstreams': '127.0.0.1:8081,127.0.0.1:8082',
        'upstream_timeout_ms': '500', 'body_bytes': '1048576'},
    5: {'cache_ttl_ms': '1000', 'cache_bytes': '4194304',
        'rate_per_second': '0', 'rate_burst': '2', 'drain_timeout_ms': '2000'},
}

def configuration(level):
    if level not in TITLES:
        raise ValueError('level must be 1 through 5')
    values = dict(BASE_CONFIG)
    for minimum, extra in EXTRA_CONFIG.items():
        if level >= minimum:
            values.update(extra)
    return values


def workloads(level):
    configuration(level)
    if level == 1:
        from stages.stage1.performance import workloads as selected
        return selected()
    if level == 2:
        from stages.stage2.performance import workloads as selected
        return selected()
    import importlib
    return importlib.import_module(f'stages.stage{level}.performance').workloads()


def specification(level, language='rust'):
    from toksec.languages import profile
    from toksec.checks import cases_for, configured_cases, EXTERNAL_CASES
    configuration(level)
    return {'version': VERSION, 'level': level, 'title': TITLES[level], 'language': language,
            'configuration': configuration(level), 'requirements': [(ROOT / name).read_text() for name in contract_files(level)],
            'profile': stage_profile(level),
            'cases': [{'id': c.id, 'description': c.description} for c in cases_for(level) + configured_cases(level) + EXTERNAL_CASES],
            'benchmarks': [asdict(w) for w in workloads(level)],
            'build': profile(language, level),
            'resources': {'server_cpu_cores': 1, 'server_address_space_mib': 512, 'server_open_files': 16384,
                          'compile_address_space_mib': 4096, 'compile_cpu_seconds': 60, 'compile_wall_seconds': 120}}


def stage_profile(level):
    configuration(level)
    return json.loads((ROOT / f'stages/stage{level}/profile.json').read_text())


def contract_files(level):
    names = ['stages/common/HTTP.md']
    if level >= 3:
        names += [f'stages/capabilities/{name}.md' for name in stage_profile(level)['capabilities'] if name != 'static-files']
    names.append(f'stages/stage{level}/SPEC.md')
    return names


def instruction_files(level, language='rust'):
    from toksec.languages import profile
    profile(language, level)
    return ['RULES.md', f'stages/languages/{language}.md', 'stages/common/INTERFACE.md', *contract_files(level), 'stages/common/BENCHMARK.md']


def packet(level, language='rust'):
    spec = specification(level, language)
    lines = [f'# Stage {level}: {TITLES[level]}', '', f'Contract version: {VERSION}.', '']
    for name in instruction_files(level, language):
        lines.extend([(ROOT / name).read_text(), ''])
    from stages.common.smoke import cases as smoke_cases
    visible = [{'id': c.id, 'description': c.description} for c in smoke_cases(level)]
    lines.extend(['## Required configuration', '', '```ini',
                  *[f'{k}={v}' for k, v in spec['configuration'].items()], '```', '',
                  '## Supplied smoke checks', '',
                  'These checks demonstrate ordinary API usage only. Design your own tests from the English requirements. Full independent grading is withheld until the run ends.', ''])
    lines.extend(f'- `{c["id"]}`: {c["description"]}' for c in visible)
    lines.extend(['', '## Workload matrix', '', '| Workload | Clients | Bytes | Connection |', '|---|---:|---:|---|'])
    lines.extend(f'| {w.id} | {w.clients} | {w.size} | {"persistent" if w.persistent else "fresh"} |' for w in workloads(level))
    lines.append('')
    return '\n'.join(lines)


def fingerprint():
    paths = list((ROOT / 'toksec').glob('*.py'))
    paths += [ROOT / name for name in ('controller.py', 'evaluator.py', 'evaluate.py', 'metering.py', 'runner.py', 'RULES.md')]
    paths += [p for p in (ROOT / 'stages').rglob('*') if p.suffix in ('.py', '.md', '.json')]
    paths += [p for p in (ROOT / 'evaluation').rglob('*') if p.suffix in ('.py', '.cpp', '.rs', '.json', '.md')]
    paths += [ROOT / 'scripts/analyze_releases.py', ROOT / 'scripts/calibrate_benchmarks.py']
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in sorted(paths))).hexdigest()


def publish(directory, language='rust'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for level in TITLES:
        (directory / f'level-{level}.md').write_text(packet(level, language))
        (directory / f'level-{level}.json').write_text(json.dumps(specification(level, language), indent=2) + '\n')
