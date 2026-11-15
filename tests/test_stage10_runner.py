import contextlib
import copy
import fcntl
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec.storage import atomic_json
from stage10 import runner
from stage10.budget import BudgetLedger, COUNT_FIELDS, MODEL


class FakeProvider:
    """A deterministic protocol fixture; never opens a network connection."""

    def __init__(self, test, run, counts=(32000,)):
        self.test, self.run = test, run
        self.counts = iter(counts)
        self.count_bodies, self.requests = [], []

    def post(self, endpoint, body, timeout):
        if endpoint == 'responses/input_tokens':
            self.count_bodies.append(copy.deepcopy(body))
            return {'object': 'response.input_tokens', 'input_tokens': next(self.counts)}
        self.test.assertEqual(endpoint, 'responses')
        self.requests.append(copy.deepcopy(body))
        self.test.assertEqual(len(self.requests), 1, 'no second generation is funded')
        self.test.assertEqual({k: v for k, v in body.items() if k in COUNT_FIELDS},
                              self.count_bodies[-1])
        report = BudgetLedger(self.run / 'budget.sqlite', '0.15').report()
        self.test.assertTrue(report['blocked'])
        self.test.assertGreater(report['held_nanodollars'], 0)
        return {'model': MODEL, 'service_tier': 'default', 'status': 'completed',
                'usage': {'input_tokens': 32000, 'output_tokens': body['max_output_tokens']},
                'output': [{'type': 'function_call', 'name': 'record_notes',
                            'arguments': json.dumps({'note': 'Retained implementation plan'})}]}


class Stage10RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        (self.run / 'candidates').mkdir()
        (self.run / 'launch-packet.md').write_text('Implement the server. Use exactly one tool.')
        atomic_json(self.run / 'manifest.json', {
            'stage': 10, 'language': 'cpp', 'model': MODEL, 'budget_usd': '0.15',
            'wall_seconds': 7200, 'started_unix': None, 'framework': runner.identity(),
            'cpus': [0], 'input_sha256': {}})
        atomic_json(self.run / 'state.json', {
            'latest': None, 'tags': [], 'notes': '', 'last_feedback': {}, 'finished': False})
        BudgetLedger(self.run / 'budget.sqlite', '0.15')

    def invoke(self, provider):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.run_loop(self.run, provider)

    def test_one_response_then_budget_stop_and_explicit_request_profile(self):
        provider = FakeProvider(self, self.run)
        result = self.invoke(provider)
        self.assertEqual(len(provider.requests), 1)
        body = provider.requests[0]
        self.assertEqual(body['model'], MODEL)
        self.assertEqual(body['service_tier'], 'default')
        self.assertEqual(body['tool_choice'], 'required')
        self.assertEqual(body['reasoning'], {'effort': 'medium'})
        self.assertEqual(body['prompt_cache_options'], {'mode': 'implicit', 'ttl': '30m'})
        self.assertEqual(body['max_output_tokens'], 9333)
        self.assertFalse(body['store'])
        self.assertEqual(body['truncation'], 'disabled')
        self.assertTrue(all(set(item) == {'role', 'content'} and isinstance(item['content'], str)
                            for item in body['input']))
        self.assertNotIn('previous_response_id', body)
        self.assertNotIn('conversation', body)
        state = runner.read(self.run)
        self.assertEqual(state['notes'], 'Retained implementation plan')
        self.assertEqual(state['stop_reason'], 'budget reservation capacity exhausted')
        self.assertTrue(state['finished'])
        self.assertIn('no_submission', result)
        ledger = BudgetLedger(self.run / 'budget.sqlite', '0.15').report()
        self.assertEqual(ledger['spent_nanodollars'], 86_665_000)
        self.assertEqual(ledger['held_nanodollars'], 0)

    def test_oversize_context_is_recounted_before_generation(self):
        artifact = self.run / 'candidates' / 'source'
        artifact.mkdir()
        (artifact / 'main.cpp').write_text('// retained source\n')
        state = runner.read(self.run)
        state.update(latest='source', notes='n' * 12000, last_feedback={'diagnostic': 'x' * 16000})
        atomic_json(self.run / 'state.json', state)
        provider = FakeProvider(self, self.run, (33000, 32000))
        self.invoke(provider)
        self.assertEqual(len(provider.count_bodies), 2)
        first = json.loads(provider.count_bodies[0]['input'][1]['content'].split('\n')[0])
        second = json.loads(provider.count_bodies[1]['input'][1]['content'].split('\n')[0])
        self.assertIn('latest_source', first)
        self.assertNotIn('latest_source', second)
        self.assertEqual(len(second['notes']), 8000)
        self.assertLessEqual(len(second['last_feedback']), 12000)
        self.assertEqual(len(provider.requests), 1)

    def test_restart_and_simultaneous_start_fail_before_provider(self):
        provider = FakeProvider(self, self.run)
        with (self.run / 'run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.invoke(provider)
        self.assertEqual(provider.count_bodies, [])
        self.invoke(provider)
        with self.assertRaisesRegex(ValueError, 'resume is disabled'):
            self.invoke(provider)
        self.assertEqual(len(provider.requests), 1)

    def test_first_read_survives_another_read_in_third_request(self):
        fixtures = self.run / 'builder-inputs' / 'fixtures'
        fixtures.mkdir(parents=True)
        (fixtures / 'first.txt').write_text('FIRST_FIXTURE_CONTENT\n')
        (fixtures / 'second.txt').write_text('SECOND_FIXTURE_CONTENT\n')
        manifest = runner.read(self.run, 'manifest.json')
        manifest.update(wall_seconds=100, input_sha256={
            'fixtures/first.txt': 'fixture', 'fixtures/second.txt': 'fixture'})
        atomic_json(self.run / 'manifest.json', manifest)
        requests = []
        testcase = self

        class ReadingProvider:
            def post(self, endpoint, body, timeout):
                if endpoint == 'responses/input_tokens':
                    return {'object': 'response.input_tokens', 'input_tokens': 1000}
                testcase.assertEqual(endpoint, 'responses')
                requests.append(copy.deepcopy(body))
                turn = len(requests)
                testcase.assertLessEqual(turn, 3)
                if turn < 3:
                    name = 'read_input'
                    args = {'path': 'fixtures/first.txt' if turn == 1 else 'fixtures/second.txt',
                            'start_line': 1, 'line_count': 10}
                else:
                    context = json.loads(body['input'][1]['content'].split('\n')[0])
                    testcase.assertEqual(context['retained_reads']['fixtures/first.txt']['text'],
                                         'FIRST_FIXTURE_CONTENT')
                    testcase.assertEqual(context['retained_reads']['fixtures/second.txt']['text'],
                                         'SECOND_FIXTURE_CONTENT')
                    testcase.assertEqual(context['last_feedback']['result']['text'],
                                         'SECOND_FIXTURE_CONTENT')
                    testcase.assertEqual([a['arguments']['path'] for a in context['recent_actions']],
                                         ['fixtures/first.txt', 'fixtures/second.txt'])
                    name, args = 'finish', {'report': 'Fixture reads retained.'}
                return {'model': MODEL, 'service_tier': 'default', 'status': 'completed',
                        'usage': {'input_tokens': 1000, 'output_tokens': 100},
                        'output': [{'type': 'function_call', 'name': name,
                                    'arguments': json.dumps(args)}]}

        self.invoke(ReadingProvider())
        self.assertEqual(len(requests), 3)
        self.assertEqual(runner.read(self.run)['stop_reason'], 'agent finished')
        self.assertEqual((self.run / 'model-report.md').read_text(), 'Fixture reads retained.')

    def test_tag_metadata_keeps_only_previous_tag_summary(self):
        def fake_git(run, *args):
            if args[0] == 'init':
                (Path(run) / 'repository' / '.git').mkdir(parents=True)
            return ''
        tags = []
        with patch.object(runner, 'git', side_effect=fake_git):
            for i in range(5):
                artifact = self.run / 'candidates' / f'source{i}'
                artifact.mkdir()
                (artifact / 'main.cpp').write_text(f'int main() {{ return {i}; }}\n')
                atomic_json(artifact / 'report.json', {'build': {'passed': True},
                    'checks': {'passed': True, 'cases': [{'id': 'bootstrap', 'passed': True}]}})
                state = runner.read(self.run)
                state['latest'] = artifact.name
                atomic_json(self.run / 'state.json', state)
                tags.append(runner.release(self.run, 'Working checkpoint', initialize=i == 0))
        self.assertIsNone(tags[0]['capacity']['last_tag'])
        for previous, current in zip(tags, tags[1:]):
            self.assertEqual(current['capacity']['last_tag'],
                             {'tag': previous['tag'], 'passed_checks': ['bootstrap']})
            self.assertNotIn('capacity', current['capacity']['last_tag'])
        self.assertLess(abs(len(json.dumps(tags[-1])) - len(json.dumps(tags[1]))), 100)


if __name__ == '__main__':
    unittest.main()
