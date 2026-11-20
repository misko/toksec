import json
from pathlib import Path

from toksec.storage import atomic_json
from toksec import controller
from toksec.languages import source_name

ROLLOVER_INPUT = 48_000


def builder_capacity(capacity):
    keys = ('spent_usd_upper_bound', 'reserved_usd', 'remaining_usd', 'remaining',
            'seconds_remaining', 'can_finish', 'work_phase', 'last_tag', 'latest_source_sha256',
            'last_benchmark', 'last_qualified_benchmark')
    return {key: capacity[key] for key in keys if key in capacity}


def checkpoint(run, launch_text):
    run = Path(run)
    state = controller.read(run)
    candidates = []
    for identity in dict.fromkeys([state['best'], state['last']]):
        if not identity:
            continue
        folder = run / 'candidates' / identity
        report = controller.read(folder, 'report.json')
        source = (folder / source_name(controller.read(run, 'manifest.json'))).read_text()
        candidate = {'id': identity, 'retained': identity == state['best'],
                     'source_sha256': report['source_sha256'], 'characters': len(source),
                     'build_passed': report['build']['passed'], 'visible_checks': sorted(controller.passed(report))}
        if len(source) <= 8000:
            candidate['source'] = source
        else:
            candidate['source_access'] = 'Use read_source with source_sha256 and a bounded line range.'
        candidates.append(candidate)
    journal = [json.loads(p.read_text()) for p in sorted((run / 'iterations').glob('*.json'))[-1:]]
    recent = []
    for path in sorted(run.glob('tool-*.json'), key=lambda p: p.stat().st_mtime)[-3:]:
        record = json.loads(path.read_text())
        value = record['result']
        recent.append({'tool': record['name'], 'error': value.get('error'), 'decision': value.get('decision'),
                       'passed': value.get('passed'), 'test_passed': value.get('tests', {}).get('passed'),
                       'candidate': value.get('candidate') or value.get('id')})
    last_failed_test = None
    for path in sorted((run / 'unit-tests').glob('*/test-result.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        result = json.loads(path.read_text())
        tests = result.get('tests', {})
        if not result['passed'] or not tests.get('passed'):
            last_failed_test = {'mode': result.get('mode', 'standalone'), 'source_sha256': result.get('source_sha256'),
                                'test_sha256': result['test_sha256'], 'compiled': result['passed'],
                                'exit_code': tests.get('exit_code'),
                                'diagnostics': (tests.get('error') or tests.get('output') or result.get('diagnostics', ''))[-2000:]}
            break
    value = {'notice': 'Same run after context rollover. No budget reset. Earlier messages are archived. Continue the improvement loop from this evidence.',
             'capacity': builder_capacity(controller.capacity(run)), 'candidates': candidates,
             'last_failed_test': last_failed_test,
             'recent_tool_outcomes': recent, 'model_authored_journal': journal}
    state['context_rollovers'] = state.get('context_rollovers', 0) + 1
    atomic_json(run / 'state.json', state)
    folder = run / 'checkpoints'
    folder.mkdir(exist_ok=True)
    atomic_json(folder / f"{state['context_rollovers']:04d}.json", value)
    return [{'role': 'developer', 'content': launch_text}, {'role': 'user', 'content': json.dumps(value)}]
