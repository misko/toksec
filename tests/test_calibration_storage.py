import hashlib
from pathlib import Path
import unittest
from toksec.calibrations import identity
from toksec.result_storage import read

class CalibrationStorageTests(unittest.TestCase):
    def test_historical_bytes_and_missing_commit_are_preserved(self):
        root = Path(__file__).resolve().parents[1] / 'calibrations'
        for p in root.glob('*/provenance/migration.json'):
            record = read(p.parent.parent / 'record.json')
            self.assertIsNone(record['toksec_commit'])
            for entry in read(p)['files'].values():
                self.assertEqual(hashlib.sha256((p.parent.parent / entry['path']).read_bytes()).hexdigest(), entry['sha256'])
        self.assertEqual(len(read(root/'index.json')['calibrations']), 1)

    def test_new_ids_are_distinct_and_commit_labeled(self):
        first = identity('a'*40)
        self.assertRegex(first, r'^calibration__static-http__\d{8}T\d{6}Z__a{12}__[a-f0-9]{8}$')
        self.assertNotEqual(first, identity('a'*40))
