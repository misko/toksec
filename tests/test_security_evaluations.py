import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from toksec.artifacts import validate_evaluation, CONTRACTS
from toksec.result_storage import publish_run, files, require_evaluation_envelopes, verify
from toksec.security_evaluations import record_security_evaluation, verify_security_files
from toksec.storage import atomic_json
import test_result_storage


class SecurityEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run, self.release = test_result_storage.RawPublicationTests().run_fixture(self.root)
        self.report = self.root / 'report.md'
        self.report.write_text('# Security analysis\nLimited parser review.\n')
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir()
        (self.evidence / 'request.bin').write_bytes(b'GET / HTTP/1.1\r\n\x00\r\n')
        self.analysis = {'evaluator_sha256': 'e' * 64, 'environment': {'os': 'test'},
                         'status': 'partial', 'scope': 'HTTP parser', 'methods': ['manual review'],
                         'limitations': ['No exhaustive analysis'],
                         'findings': [{'id': 'S1', 'title': 'Parser concern', 'severity': 'low',
                                       'status': 'unconfirmed', 'description': 'Needs reproduction.',
                                       'evidence': ['evidence/request.bin']}]}

    def record(self, identity='security-one'):
        return record_security_evaluation(self.run, tag=self.release['tag'],
            analysis=self.analysis, report=self.report, evidence=self.evidence,
            evaluation_id=identity)

    def test_historical_import_resolves_tag_without_release_json_tag(self):
        import hashlib
        import shutil
        from toksec.artifacts import artifact_contract
        from toksec.result_storage import publish_run, verify
        from toksec.storage import atomic_json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, release = test_result_storage.RawPublicationTests().run_fixture(root)
            repository = run / 'repository'
            # Reconstruct the historical shape: no frozen contract and no tag field.
            (run / 'artifact.json').unlink()
            raw = json.loads((repository / 'release.json').read_text())
            raw.pop('tag')
            atomic_json(repository / 'release.json', raw)
            git = lambda *a: __import__('subprocess').check_output(
                ['git', '-C', str(repository), '-c', 'user.name=T', '-c', 'user.email=t@e.invalid',
                 '-c', 'commit.gpgsign=false', *a], stderr=subprocess.DEVNULL)
            git('add', 'release.json')
            git('commit', '-m', 'strip tag for historical import test')
            git('tag', '-f', 'release/000001')
            release['commit'] = git('rev-parse', 'release/000001^{commit}').decode().strip()
            reconstructed = root / 'reconstructed-artifact.json'
            atomic_json(reconstructed, artifact_contract(1, 'cpp'))
            report = root / 'report.md'
            report.write_text('# Historical analysis\n')
            evidence = root / 'evidence'
            evidence.mkdir()
            (evidence / 'probe.txt').write_text('output\n')
            analysis = {'evaluator_sha256': 'f' * 64, 'environment': {'os': 'test'},
                        'status': 'completed', 'scope': 'historical scope', 'methods': ['review'],
                        'limitations': ['reconstructed metadata'],
                        'findings': [{'id': 'H1', 'title': 'Historical finding', 'severity': 'low',
                                      'status': 'confirmed', 'description': 'Observed.',
                                      'evidence': ['evidence/probe.txt']}]}
            record = record_security_evaluation(run, tag='release/000001', analysis=analysis,
                report=report, evidence=evidence, evaluation_id='security-import',
                artifact=reconstructed)
            self.assertEqual(record['provenance']['mode'], 'historical_import')
            self.assertEqual(record['provenance']['contract_provenance'], 'reconstructed_for_storage')
            self.assertIn('omitted the tag', record['provenance']['release_metadata'])
            self.assertIsNone(record['run_toksec_commit'])
            self.assertEqual(record['release']['tag'], 'release/000001')
            self.assertEqual(record['release']['commit'], release['commit'])
            # The envelope carries its own contract for later verification.
            self.assertTrue((run / 'evaluation/security-import/artifact.json').is_file())
            publish_run(run, root / 'results')
            verify(root / 'results' / run.name)
            published = root / 'results' / run.name / 'evaluation/security-import'
            self.assertEqual((published / 'report.md').read_bytes(), report.read_bytes())

    def test_report_only_folder_requires_registration_without_reading_report(self):
        directory = self.run / 'evaluation/security-unregistered'
        directory.mkdir(parents=True)
        (directory / 'report.md').write_text('Unread report')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('report read')):
            with self.assertRaisesRegex(ValueError, 'record_security_evaluation.py'):
                require_evaluation_envelopes(self.run)
        with self.assertRaisesRegex(ValueError, 'missing evaluation.json'):
            publish_run(self.run, self.root / 'results')

    def test_published_report_only_folder_is_rejected(self):
        self.record()
        publish_run(self.run, self.root / 'results')
        published = self.root / 'results' / self.run.name
        directory = published / 'evaluation/security-unregistered'
        directory.mkdir()
        (directory / 'report.md').write_text('Unread report')
        with self.assertRaisesRegex(ValueError, 'unregistered evaluation report'):
            verify(published)

    def test_publishes_report_binary_evidence_and_exact_release(self):
        record = self.record()
        self.assertEqual(record['release']['commit'], self.release['commit'])
        publish_run(self.run, self.root / 'results')
        target = self.root / 'results' / self.run.name / 'evaluation/security-one'
        self.assertEqual((target / 'evidence/request.bin').read_bytes(), (self.evidence / 'request.bin').read_bytes())
        self.assertEqual((target / 'report.md').read_bytes(), self.report.read_bytes())
        verify_security_files(target, record)
        before = files(target)
        self.record('security-two')
        publish_run(self.run, self.root / 'results')
        self.assertEqual(files(target), before)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.record()
        with (self.run / 'evaluation/security-one/report.md').open('a') as report:
            report.write('tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            publish_run(self.run, self.root / 'results')
        self.assertEqual(files(target), before)

    def test_rejects_wrong_release_run_and_contract(self):
        original = self.record()
        path = self.run / 'evaluation/security-one/evaluation.json'
        for field, value in [('run_id', 'different'), ('contract_sha256', 'f' * 64),
                             ('commit', 'b' * 40), ('source_sha256', 'b' * 64), ('tag', 'release/999999')]:
            with self.subTest(field=field):
                record = copy.deepcopy(original)
                (record['release'] if field in record['release'] else record)[field] = value
                atomic_json(path, record)
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    publish_run(self.run, self.root / 'results')

    def test_older_release_and_api_grade_remain_independent(self):
        import hashlib
        from toksec.releases import git
        from toksec.evaluation_artifacts import write_evaluation
        from toksec.result_storage import digest
        repository = self.run / 'repository'
        source = b'int main() { return 1; }\n'
        (repository / 'main.cpp').write_bytes(source)
        meta = {'tag': 'release/000002', 'candidate': 'candidate-two',
                'source_sha256': hashlib.sha256(source).hexdigest()}
        atomic_json(repository / 'release.json', meta)
        git(self.run, 'add', 'main.cpp', 'release.json')
        git(self.run, '-c', 'commit.gpgsign=false', 'commit', '-m', 'Second release')
        git(self.run, 'tag', meta['tag'])
        record = self.record()
        self.assertEqual(record['release']['commit'], self.release['commit'])
        write_evaluation(self.run / 'evaluation/api-one', run_id=self.run.name,
            release=self.release, contract_sha256=digest(self.run / 'artifact.json'),
            evaluator_sha256='a' * 64, environment={}, coverage='full',
            result={'checks': {'passed': True, 'cases': [{'id': 'test', 'passed': True}]}})
        publish_run(self.run, self.root / 'results')
        target = self.root / 'results' / self.run.name / 'evaluation'
        self.assertEqual(json.loads((target / 'api-one/evaluation.json').read_text())['api']['status'], 'passed')
        self.assertEqual(json.loads((target / 'security-one/evaluation.json').read_text())['release'], record['release'])

    def test_rejects_traversal_duplicate_paths_and_missing_evidence(self):
        original = self.record()
        for name in ('../secret', '/tmp/secret', 'evidence/../secret', 'evidence//secret', 'evidence/./secret', 'evidence\\secret'):
            record = copy.deepcopy(original)
            record['artifacts'][0]['path'] = name
            with self.assertRaises(ValueError):
                validate_evaluation(record)
        for mutation in ('duplicate', 'missing', 'api'):
            record = copy.deepcopy(original)
            if mutation == 'duplicate': record['artifacts'].append(record['artifacts'][0])
            if mutation == 'missing': record['findings'][0]['evidence'] = ['evidence/absent']
            if mutation == 'api': record['api'] = {'status': 'passed'}
            with self.assertRaises(ValueError):
                validate_evaluation(record)

    def test_unlisted_files_and_symlinks_are_rejected(self):
        record = self.record()
        directory = self.run / 'evaluation/security-one'
        extra = directory / 'evidence/unlisted.txt'
        extra.write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            verify_security_files(directory, record)
        extra.unlink()
        extra.symlink_to(self.report)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            publish_run(self.run, self.root / 'results')

    def test_cli_and_schema(self):
        analysis = self.root / 'analysis.json'
        atomic_json(analysis, self.analysis)
        command = [sys.executable, 'scripts/record_security_evaluation.py', '--run', str(self.run),
                   '--tag', self.release['tag'], '--analysis', str(analysis), '--report', str(self.report),
                   '--evidence', str(self.evidence), '--evaluation-id', 'security-cli']
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        record = json.loads(done.stdout)
        self.assertNotIn('api', record)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("Optional JSON Schema validator is not installed")
        schema = json.loads((CONTRACTS / 'security-evaluation.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(record)
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
