import json
from pathlib import Path
import tempfile
import unittest

from toksec.provenance import run_identity, run_name
from toksec.result_storage import publish_run, read, files
from toksec.storage import atomic_json


class PublicationIdentityTests(unittest.TestCase):
    def raw(self, root, start=1, legacy=False):
        identity = 'legacy' if legacy else run_name(1, 'cpp', 'a' * 40)
        run = root / identity
        run.mkdir()
        manifest = {'stage': 1, 'language': 'cpp', 'started_unix': start,
                    'builder_evaluation_scope': 'visible_smoke_only', 'campaign': str(root),
                    'wall_seconds': 20, 'model': 'test'}
        if not legacy:
            manifest.update(run_id=identity, toksec_commit='a' * 40)
        atomic_json(run / 'manifest.json', manifest)
        atomic_json(run / 'state.json', {'finished': False})
        atomic_json(run / 'specification.json', {'version': 'old'})
        atomic_json(root / 'ledger.json', {'dollar_limit': '3'})
        (run / 'launch-packet.md').write_text('instructions')
        return run

    def test_one_identity_survives_move_and_republication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root); identity = run.name
            out = root / 'results'
            first = publish_run(run, out)
            moved = root / 'moved'; run.rename(moved)
            second = publish_run(moved, out)
            for field in ('id', 'run_id', 'raw_run_id', 'path'):
                self.assertEqual(first[field], identity)
                self.assertEqual(second[field], identity)
            self.assertEqual(len(read(out / 'index.json')['all_runs']), 1)

    def test_out_of_order_publications_preserve_all_and_select_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old = self.raw(root, 1.1); new = self.raw(root, 1.9)
            out = root / 'results'
            publish_run(new, out); before = files(out / new.name)
            publish_run(old, out)
            self.assertEqual(read(out / 'index.json')['runs'][0]['id'], new.name)
            self.assertEqual(len(read(out / 'index.json')['all_runs']), 2)
            self.assertEqual(files(out / new.name), before)

    def test_legacy_missing_provenance_stays_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root, legacy=True)
            record = publish_run(run, root / 'results')
            self.assertEqual(record['id'], 'legacy')
            self.assertIsNone(record['framework'])
            self.assertNotIn('toksec_commit', record)

    def test_collision_rejected_without_changing_published_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root); out = root / 'results'
            publish_run(run, out); before = files(out / run.name)
            (run / 'launch-packet.md').write_text('different instructions')
            with self.assertRaisesRegex(ValueError, 'collision'):
                publish_run(run, out)
            self.assertEqual(files(out / run.name), before)

    def test_persisted_identity_requires_matching_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root)
            manifest = read(run / 'manifest.json')
            for identity in ('../escape', '/tmp/escape', 'wrong', run_name(2, 'cpp', 'a'*40)):
                with self.subTest(identity=identity), self.assertRaises(ValueError):
                    run_identity(run, dict(manifest, run_id=identity))
            with self.assertRaises(ValueError):
                run_identity(run, dict(manifest, toksec_commit='b'*40))

    def test_symlink_destination_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root); out = root / 'results'; out.mkdir()
            (out / run.name).symlink_to(root / 'elsewhere')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                publish_run(run, out)

    def test_running_can_finish_without_reassigning_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = self.raw(root); out = root / 'results'
            publish_run(run, out)
            atomic_json(run / 'state.json', {'finished': True})
            record = publish_run(run, out)
            self.assertEqual(record['status'], 'builder_finished')
            self.assertEqual(record['id'], run.name)

    def test_parent_evaluations_append_and_cannot_change(self):
        from test_result_storage import RawPublicationTests
        from toksec.evaluation_artifacts import write_evaluation
        from toksec.result_storage import digest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run, release = RawPublicationTests().run_fixture(root)
            out = root / 'results'
            def evaluate(name):
                write_evaluation(run / 'evaluation' / name, run_id=run.name, release=release,
                    contract_sha256=digest(run / 'artifact.json'), evaluator_sha256='a'*64,
                    environment={}, coverage='full', result=None)
            evaluate('one'); publish_run(run, out)
            previous = files(out / run.name / 'evaluation/one')
            evaluate('two'); publish_run(run, out)
            self.assertEqual(files(out / run.name / 'evaluation/one'), previous)
            self.assertTrue((out / run.name / 'evaluation/two/evaluation.json').exists())
            (run / 'evaluation/one/report.md').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evaluation identity collision'):
                publish_run(run, out)
            self.assertEqual(files(out / run.name / 'evaluation/one'), previous)
