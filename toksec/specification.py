from toksec.stages import identifier as stage_id
import hashlib
import json
from dataclasses import asdict
from stages.common.grading.performance import Workload, matrix
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLES = {1: 'Static files', 2: 'Concurrent persistent HTTP', 3: 'Hosts and routing',
          4: 'Reverse proxy', 5: 'Plaintext operations'}
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
    from toksec.stages import module
    configuration(level)
    return module(level, 'performance').workloads()


def specification(level, language='rust'):
    if level == 10:
        from toksec.stages import module as stage_module
        input_files = stage_module(10, 'packet').input_files
        from toksec.languages import profile
        return {'stage': 10, 'language': language,
                'title': 'Configuration, HTTPS, and worker operations', 'api_coverage': 'partial',
                'performance_scope': 'provisional', 'final_grade_eligible': False,
                'build': profile(language, 10), 'configuration_format': 'nginx subset',
                'instructions': list(input_files(language)),
                'diagnostics': ['http-256', 'http-4096', 'https-256', 'https-4096']}
    from toksec.languages import profile
    from toksec.checks import cases_for, configured_cases, EXTERNAL_CASES
    configuration(level)
    return {'stage': level, 'title': TITLES[level], 'language': language,
            'configuration': configuration(level), 'requirements': [(ROOT / name).read_text() for name in contract_files(level)],
            'profile': stage_profile(level),
            'cases': [{'id': c.id, 'description': c.description} for c in cases_for(level) + configured_cases(level) + EXTERNAL_CASES],
            'benchmarks': [asdict(w) for w in workloads(level)],
            'build': profile(language, level),
            'resources': {'server_cpu_cores': 1, 'server_address_space_mib': 512, 'server_open_files': 16384,
                          'compile_address_space_mib': 4096, 'compile_cpu_seconds': 60, 'compile_wall_seconds': 120}}


def stage_profile(level):
    configuration(level)
    return json.loads((ROOT / f'stages/{stage_id(level)}/profile.json').read_text())


def contract_files(level):
    names = ['stages/common/HTTP.md']
    if level >= 3:
        names += [f'stages/capabilities/{name}.md' for name in stage_profile(level)['capabilities'] if name != 'static-files']
    names.append(f'stages/{stage_id(level)}/SPEC.md')
    return names


def instruction_files(level, language='rust'):
    from toksec.languages import profile
    profile(language, level)
    return ['RULES.md', f'stages/languages/{language}.md', 'stages/common/INTERFACE.md', 'stages/common/ARTIFACTS.md', *contract_files(level), 'stages/common/BENCHMARK.md']


def packet(level, language='rust'):
    if level == 10:
        from toksec.stages import module as stage_module
        selected = stage_module(10, 'packet').packet
        return selected(language)
    from toksec.artifacts import artifact_contract
    spec = specification(level, language)
    lines = [f'# Stage {level}: {TITLES[level]}', '']
    for name in instruction_files(level, language):
        lines.extend([(ROOT / name).read_text(), ''])
    lines.extend(['## Artifact contract', '', '```json', json.dumps(artifact_contract(level, language), indent=2, sort_keys=True), '```', ''])
    from stages.common.smoke.api import cases as smoke_cases
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
    paths = list((ROOT / 'toksec').rglob('*.py'))
    paths += [ROOT / name for name in ('evaluate.py', 'RULES.md')]
    paths += [p for p in (ROOT / 'stages').rglob('*') if p.suffix in ('.py', '.md', '.json', '.cpp', '.rs') and not p.is_relative_to(ROOT / 'stages/stage-10')]
    paths += list((ROOT / 'contracts').glob('*.schema.json'))
    paths += [ROOT / 'fixtures/accounting/legacy-pilot-ledger.json']
    paths += [ROOT / 'scripts/analyze_releases.py', ROOT / 'scripts/calibrate_benchmarks.py']
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in sorted(paths))).hexdigest()


def publish(directory, language='rust', level=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    selected_levels = [level] if level is not None else TITLES
    for level in selected_levels:
        (directory / f'{stage_id(level)}.md').write_text(packet(level, language))
        (directory / f'{stage_id(level)}.json').write_text(json.dumps(specification(level, language), indent=2) + '\n')


def counted_fingerprint():
    from toksec.stages import module as stage_module
    input_files = stage_module(10, 'packet').input_files
    paths = list((ROOT / 'toksec').rglob('*.py'))
    paths += list((ROOT / 'stages/stage-10').rglob('*'))
    paths = [p for p in paths if p.is_file() and '__pycache__' not in p.parts]
    for language in ('cpp', 'rust'):
        paths.extend(input_files(language).values())
    paths += list((ROOT / 'contracts').glob('*.schema.json'))
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes()
                                  for p in sorted(set(paths)))).hexdigest()
