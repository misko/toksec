import json
from pathlib import Path

from controller import atomic_json
from toksec import controller

ROLLOVER_INPUT = 48_000


def checkpoint(run, launch_text):
    run = Path(run)
    state = controller.read(run)
    candidates = []
    for identity in dict.fromkeys([state['best'], state['last']]):
        if not identity:
            continue
        folder = run / 'candidates' / identity
        report = controller.read(folder, 'report.json')
        candidates.append({'id': identity, 'retained': identity == state['best'],
                           'source': (folder / 'main.rs').read_text(), 'report': report})
    journal = [json.loads(p.read_text()) for p in sorted((run / 'iterations').glob('*.json'))[-3:]]
    recent = []
    for path in sorted(run.glob('tool-*.json'), key=lambda p: p.stat().st_mtime)[-3:]:
        record = json.loads(path.read_text())
        value = record['result']
        recent.append({'tool': record['name'], 'error': value.get('error'), 'decision': value.get('decision'),
                       'passed': value.get('passed'), 'tests': value.get('tests'),
                       'candidate': value.get('candidate') or value.get('id')})
    measurements = []
    for path in sorted((run / 'candidates').glob('*/benchmark.json'), key=lambda p: p.stat().st_mtime)[-2:]:
        result = json.loads(path.read_text())
        measurements.append({'candidate': result['candidate'], 'decision': result['decision'],
                             'summaries': {identity: {name: {key: metric for key, metric in summary.items() if key != 'rounds'}
                                                     for name, summary in work.items()}
                                           for identity, work in result['summaries'].items()}})
    value = {'notice': 'Same run after context rollover. No budget reset. Earlier messages are archived. Continue the improvement loop from this evidence.',
             'state': state, 'capacity': controller.capacity(run), 'candidates': candidates,
             'recent_tool_outcomes': recent, 'model_authored_journal': journal, 'benchmark_evidence': measurements}
    state['context_rollovers'] = state.get('context_rollovers', 0) + 1
    atomic_json(run / 'state.json', state)
    folder = run / 'checkpoints'
    folder.mkdir(exist_ok=True)
    atomic_json(folder / f"{state['context_rollovers']:04d}.json", value)
    return [{'role': 'developer', 'content': launch_text}, {'role': 'user', 'content': json.dumps(value)}]
