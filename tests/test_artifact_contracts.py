import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec import artifacts


class ArtifactContractTests(unittest.TestCase):
    def evaluation(self):
        return {'schema_version': 1, 'run_id': 'run-1',
                'release': {'tag': 'release/000001', 'commit': 'a'*40,
                            'source_sha256': 'b'*64},
                'contract_sha256': 'c'*64, 'evaluator_sha256': 'd'*64,
                'provenance_status': 'verified', 'missing_evidence': [],
                'environment': {'cpu_count': 1}, 'coverage': 'full', 'status': 'passed',
                'api': {'status': 'passed', 'passed': 12, 'total': 12},
                'performance': {'status': 'not_run', 'credit': None, 'metrics': None}}

    def test_all_stage_language_contracts_and_source_names(self):
        for stage in range(1, 11):
            for language, filename in [('cpp', 'main.cpp'), ('rust', 'main.rs')]:
                with self.subTest(stage=stage, language=language):
                    contract = artifacts.artifact_contract(stage, language)
                    self.assertEqual(contract['submission']['source_file'], filename)
                    self.assertEqual(artifacts.validate_artifact(contract), contract)
        for stage, language in [(0, 'cpp'), (11, 'cpp'), (True, 'cpp'), (1, 'python')]:
            with self.assertRaises(ValueError):
                artifacts.artifact_contract(stage, language)

    def test_source_filename_and_unexpected_fields_are_rejected(self):
        for filename in ['main.rs', '../main.cpp', '/main.cpp']:
            contract = artifacts.artifact_contract(1, 'cpp')
            contract['submission']['source_file'] = filename
            with self.assertRaises(ValueError):
                artifacts.validate_artifact(contract)
        contract = artifacts.artifact_contract(1, 'cpp')
        contract['destination'] = '/tmp/publish-here'
        with self.assertRaises(ValueError):
            artifacts.validate_artifact(contract)

    def test_utf8_byte_limit_is_not_character_limit(self):
        contract = artifacts.artifact_contract(1, 'cpp')
        self.assertEqual(artifacts.validate_source('x' * 1048576, contract), 'x' * 1048576)
        for source in ['x' * 1048577, 'é' * 524289, '\ud800', b'bytes']:
            with self.assertRaises(ValueError):
                artifacts.validate_source(source, contract)

    def test_frozen_contract_is_supplied_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            contract = artifacts.write_artifact(run, 10, 'cpp')
            raw = (run/'artifact.json').read_bytes()
            self.assertEqual(raw, (run/'builder-inputs/artifact.json').read_bytes())
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(artifacts.read_artifact(run, 10, 'cpp', digest), contract)
            with self.assertRaises(ValueError):
                artifacts.read_artifact(run, 1, 'cpp', digest)
            (run/'artifact.json').write_bytes(raw + b'\n')
            with self.assertRaises(ValueError):
                artifacts.read_artifact(run, 10, 'cpp', digest)
            (run/'artifact.json').unlink()
            with self.assertRaises(FileNotFoundError):
                artifacts.read_artifact(run, 10, 'cpp', digest)
            self.assertEqual(artifacts.read_artifact(run, 10, 'cpp'), contract)

    def test_verified_evaluation_requires_identity_and_complete_api(self):
        self.assertEqual(artifacts.validate_evaluation(self.evaluation()), self.evaluation())
        for mutation in [lambda e: e.update(coverage='partial'),
                         lambda e: e['release'].update(commit=None),
                         lambda e: e.update(evaluator_sha256=None),
                         lambda e: e['api'].update(passed=11),
                         lambda e: e['api'].update(passed=None),
                         lambda e: e['api'].update(passed=0,total=0)]:
            value = self.evaluation(); mutation(value)
            with self.assertRaises(ValueError):
                artifacts.validate_evaluation(value)

    def test_historical_incomplete_identity_is_explicit(self):
        value = self.evaluation()
        value.update(status='partial', coverage='unknown', provenance_status='historical_incomplete',
                     evaluator_sha256=None, missing_evidence=['evaluator_sha256', 'release.commit'])
        value['release']['commit'] = None
        artifacts.validate_evaluation(value)
        value['missing_evidence'] = []
        with self.assertRaises(ValueError):
            artifacts.validate_evaluation(value)

    def test_failed_api_skips_performance_without_invented_metrics(self):
        value = self.evaluation()
        value.update(status='failed')
        value['api'].update(status='failed',passed=10)
        with self.assertRaises(ValueError):
            artifacts.validate_evaluation(value)
        value['performance'] = {'status':'skipped_api_failure','credit':0,'metrics':None}
        artifacts.validate_evaluation(value)
        value['performance']['metrics'] = {'requests_per_second': 0}
        with self.assertRaises(ValueError):
            artifacts.validate_evaluation(value)

    def test_build_failure_can_fail_gate_before_any_cases_run(self):
        value = self.evaluation()
        value.update(status='failed')
        value['api'] = {'status':'failed','passed':0,'total':0}
        value['performance'] = {'status':'skipped_api_failure','credit':0,'metrics':None}
        artifacts.validate_evaluation(value)
        value['api'].update(passed=12,total=12)
        artifacts.validate_evaluation(value)

    def test_measured_performance_requires_full_verified_api_and_metrics(self):
        value = self.evaluation()
        value['performance'] = {'status':'measured','credit':None,'metrics':{'requests_per_second':100}}
        artifacts.validate_evaluation(value)
        value.update(coverage='partial', status='partial')
        with self.assertRaises(ValueError):
            artifacts.validate_evaluation(value)
        value['performance'] = {'status':'skipped_incomplete_suite','credit':None,'metrics':None}
        artifacts.validate_evaluation(value)

    def test_invalid_measurement_preserves_evidence_with_zero_credit(self):
        value = self.evaluation()
        value['performance'] = {'status':'invalid_measurement','credit':0,
                                'metrics':{'generator_saturated':True,'requests_per_second':100}}
        artifacts.validate_evaluation(value)
        value['performance']['credit'] = None
        with self.assertRaises(ValueError):
            artifacts.validate_evaluation(value)

    def test_unsupported_schema_keywords_fail_instead_of_being_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            schema = json.loads((artifacts.CONTRACTS/'artifact.schema.json').read_text())
            schema['allOf'][0]['if']['unknownKeyword'] = True
            (directory/'artifact.schema.json').write_text(json.dumps(schema))
            with patch.object(artifacts, 'CONTRACTS', directory), self.assertRaises(ValueError):
                artifacts.artifact_contract(1, 'cpp')

    def test_published_schemas_are_valid_json_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional independent JSON Schema validator is not installed')
        for name in ('artifact','evaluation'):
            schema = json.loads((artifacts.CONTRACTS/(name+'.schema.json')).read_text())
            Draft202012Validator.check_schema(schema)
            value = artifacts.artifact_contract(10,'cpp') if name == 'artifact' else self.evaluation()
            Draft202012Validator(schema).validate(value)
