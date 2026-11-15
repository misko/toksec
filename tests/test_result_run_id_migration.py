import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toksec.result_migration import migrate_run_ids, verify_relocation, MAPPING
from toksec.result_storage import files, publish_snapshot, read, verify
from toksec.storage import atomic_json


class RunIdMigrationTests(unittest.TestCase):
    def fixture(self, root, stage=1, identity='old-raw-id'):
        snapshot = root / f'flat-{stage}'
        snapshot.mkdir()
        record = {'id': f'old-publication-{stage}', 'stage': stage, 'language': 'cpp',
                  'protocol': 'historical', 'framework': 'a' * 64, 'status': 'partially_graded',
                  'started_utc': '2026-11-15', 'source_run': f'/original/campaign/{identity}',
                  'path': f'stage-{stage:02d}/cpp'}
        atomic_json(snapshot / 'run.json', record)
        (snapshot / 'launch-packet.md').write_text('Historical instructions')
        (snapshot / 'correctness.svg').write_text('<svg>historical figure</svg>')
        (snapshot / 'README.md').write_text('Original report')
        (snapshot / 'ledger.json').write_text('{"spent": 1}')
        publish_snapshot(snapshot, root / 'results')
        return root / f'results/stage-{stage:02d}/cpp'

    def test_preserves_every_original_file_and_historical_evaluation_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            before = files(source)
            index_before = (root / 'results/index.json').read_bytes()
            preview = migrate_run_ids(root / 'results')
            self.assertEqual(preview[0]['destination'], 'old-raw-id')
            self.assertEqual(files(source), before)
            migrate_run_ids(root / 'results', apply=True)
            target = root / 'results/old-raw-id'
            self.assertFalse(source.exists())
            mapping = verify_relocation(target)
            for name, expected in before.items():
                self.assertEqual(files(target)[mapping['files'][name]['path']], expected)
            record = read(target / 'run.json')
            self.assertEqual(record['run_id'], 'old-raw-id')
            self.assertIn('old-publication-1', record['historical_ids'])
            self.assertNotIn('toksec_commit', record)
            report = next(target.glob('evaluation/*/evaluation.json'))
            self.assertEqual(read(report)['run_id'], 'old-publication-1')
            self.assertEqual((root / 'results/provenance/run-id-migration/index.json').read_bytes(), index_before)
            self.assertEqual(read(root / 'results/index.json')['runs'][0]['path'], 'old-raw-id')
            stable = files(root / 'results')
            again = migrate_run_ids(root / 'results', apply=True)
            self.assertEqual(again[0]['status'], 'already_migrated')
            self.assertEqual(files(root / 'results'), stable)
            verify(target)

    def test_destination_collision_stops_whole_batch_before_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); first = self.fixture(root)
            self.fixture(root, 2, 'second-id')
            (root / 'results/second-id').mkdir()
            before = files(first)
            with self.assertRaises((ValueError, FileNotFoundError)):
                migrate_run_ids(root / 'results', apply=True)
            self.assertEqual(files(first), before)
            self.assertFalse((root / 'results/old-raw-id').exists())

    def test_duplicate_raw_ids_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root); self.fixture(root, 2)
            with self.assertRaisesRegex(ValueError, 'collision'):
                migrate_run_ids(root / 'results', apply=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            (root / 'results/old-raw-id').symlink_to(root / 'outside')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                migrate_run_ids(root / 'results', apply=True)
            self.assertTrue(source.exists())

    def test_changed_source_is_rejected_and_figures_are_never_regraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            figure = next(source.glob('evaluation/*/figures/*.svg'))
            figure.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                migrate_run_ids(root / 'results', apply=True)
            self.assertTrue(source.exists())

    def test_retry_after_install_interruption_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            before = files(source)
            actual = verify_relocation
            calls = 0
            def interrupted(path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError('interrupted after install')
                return actual(path)
            with patch('toksec.result_migration.verify_relocation', side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                    migrate_run_ids(root / 'results', apply=True)
            self.assertEqual(files(source), before)
            self.assertTrue((root / 'results/old-raw-id').exists())
            migrate_run_ids(root / 'results', apply=True)
            self.assertFalse(source.exists())
            verify_relocation(root / 'results/old-raw-id')

    def test_retry_repairs_index_after_interrupted_index_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            with patch('toksec.result_migration._update_index', side_effect=RuntimeError('index interrupted')):
                with self.assertRaises(RuntimeError):
                    migrate_run_ids(root / 'results', apply=True)
            self.assertFalse(source.exists())
            migrate_run_ids(root / 'results', apply=True)
            self.assertEqual(read(root / 'results/index.json')['runs'][0]['path'], 'old-raw-id')
