import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('refresh_results',ROOT/'scripts/refresh_results.py')
refresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(refresh)

class ResultStorageTests(unittest.TestCase):
    def make(self,root,name,start=1,language='cpp',scope='visible_smoke_only',starter=False):
        run=root/'.runs'/name/'runs'/name;run.mkdir(parents=True)
        data={'level':1,'language':language,'started_unix':start,'builder_evaluation_scope':scope,
              'starter_candidate':'seed' if starter else None}
        (run/'manifest.json').write_text(json.dumps(data));return run

    def test_latest_per_language_excludes_more_input_and_prepared_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make(root,'old',1)
            current=self.make(root,'latest',2)
            rust=self.make(root,'rust',1,language='rust')
            self.make(root,'seed',99,starter=True)
            self.make(root,'full',100,scope='full')
            self.make(root,'unknown',101,scope=None)
            self.make(root,'prepared',None)
            selected=refresh.select([root])
            self.assertEqual(selected[(1,'cpp')][0],current)
            self.assertEqual(selected[(1,'rust')][0],rust)
            self.assertEqual(len(selected),2)

    def test_empty_roots_do_not_fabricate_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(refresh.publish([root],root/'results'),[])
            self.assertEqual(json.loads((root/'results/index.json').read_text())['runs'],[])

    def test_live_entry_does_not_copy_api_history_or_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=self.make(root,'live')
            manifest=json.loads((run/'manifest.json').read_text())
            manifest.update(campaign=str(root),fingerprint='a'*64,wall_seconds=7200,model='terra')
            (run/'manifest.json').write_text(json.dumps(manifest))
            (run/'state.json').write_text('{"finished":false}')
            (run/'specification.json').write_text('{"version":"v8"}')
            (run/'launch-packet.md').write_text('Instructions')
            (run/'response-secret.json').write_text('Do not publish')
            (root/'ledger.json').write_text('{"dollar_limit":"3"}')
            output=root/'results';refresh.publish([root],output)
            dest=output/'stage-01/cpp'
            self.assertEqual(json.loads((dest/'run.json').read_text())['status'],'running')
            self.assertFalse((dest/'response-secret.json').exists())
            self.assertFalse((dest/'ledger.json').exists())
            self.assertTrue((run/'response-secret.json').exists())

    def test_external_protocol_snapshot_survives_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'results';dest=output/'stage-10/cpp'
            dest.mkdir(parents=True)
            record={'stage':10,'language':'cpp','protocol':'stage10-experimental',
                    'status':'partially_graded','started_utc':'2026-11-15',
                    'path':'stage-10/cpp','inventory_management':'preserved_snapshot'}
            (dest/'run.json').write_text(json.dumps(record))
            (dest/'implementation.bundle').write_bytes(b'preserved artifact')
            self.assertEqual(refresh.publish([root],output),[record])
            self.assertEqual((dest/'implementation.bundle').read_bytes(),b'preserved artifact')
            self.assertIn('stage-10/cpp/README.md',(output/'README.md').read_text())
