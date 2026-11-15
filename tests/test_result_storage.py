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

class LayoutMigrationTests(unittest.TestCase):
    def snapshot(self, root, run_id='run-1'):
        from controller import atomic_json
        path=root/'legacy';path.mkdir()
        atomic_json(path/'run.json', {'id':run_id,'stage':1,'language':'cpp',
                    'protocol':'http-v7','framework':'a'*64,'status':'graded',
                    'started_utc':'2026-11-15','source_run':'/old/run',
                    'path':'stage-01/cpp'})
        (path/'README.md').write_text('Historical report')
        (path/'launch-packet.md').write_text('Original instructions')
        (path/'implementation.bundle').write_bytes(b'original bundle bytes')
        (path/'release-000001.cpp').write_text('int main() {}')
        (path/'correctness.png').write_bytes(b'original figure bytes')
        (path/'ledger.json').write_text('{"spent":1}')
        return path

    def test_migration_preserves_every_byte_and_is_idempotent(self):
        from toksec.result_storage import publish_snapshot, migrate, files, read
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.snapshot(root);before=files(source)
            output=root/'results';record=publish_snapshot(source,output);dest=output/'stage-01/cpp'
            mapping=read(dest/'migration.json')['files']
            for name,expected in before.items():
                self.assertEqual(files(dest)[mapping[name]['path']],expected)
            self.assertTrue((dest/'implementation/releases/release-000001.cpp').exists())
            self.assertEqual((dest/'implementation/implementation.bundle').read_bytes(),b'original bundle bytes')
            self.assertEqual((dest/'accounting/ledger.json').read_text(),'{"spent":1}')
            self.assertTrue(list((dest/'evaluation').glob('*/figures/correctness.png')))
            stable=files(dest)
            self.assertEqual(migrate(output,apply=True)[0]['status'],'already_migrated')
            self.assertEqual(files(dest),stable)

    def test_unclassified_file_or_symlink_fails_without_replacing_destination(self):
        from toksec.result_storage import publish_snapshot, files
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.snapshot(root);output=root/'results'
            publish_snapshot(source,output);dest=output/'stage-01/cpp';before=files(dest)
            (source/'response-secret.json').write_text('not publishable')
            with self.assertRaisesRegex(ValueError,'unclassified'):
                publish_snapshot(source,output)
            self.assertEqual(files(dest),before)
            (source/'response-secret.json').unlink()
            (source/'main.cpp').symlink_to(source/'release-000001.cpp')
            with self.assertRaisesRegex(ValueError,'symlink'):
                publish_snapshot(source,output)
            self.assertEqual(files(dest),before)

    def test_same_run_preserves_parent_evaluation_but_new_run_does_not(self):
        from toksec.result_storage import publish_snapshot, read
        from controller import atomic_json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.snapshot(root);output=root/'results'
            publish_snapshot(source,output);dest=output/'stage-01/cpp'
            custom=dest/'evaluation/parent-custom';custom.mkdir();(custom/'report.md').write_text('parent report')
            publish_snapshot(source,output)
            self.assertEqual((custom/'report.md').read_text(),'parent report')
            record=read(source/'run.json');record['id']='new-run';atomic_json(source/'run.json',record)
            publish_snapshot(source,output)
            self.assertFalse(custom.exists())

    def test_tampered_migrated_artifact_is_rejected(self):
        from toksec.result_storage import publish_snapshot, migrate
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.snapshot(root);output=root/'results'
            publish_snapshot(source,output)
            (output/'stage-01/cpp/implementation/implementation.bundle').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                migrate(output,apply=True)

class RawPublicationTests(unittest.TestCase):
    def run_fixture(self, root):
        import hashlib
        import subprocess
        from controller import atomic_json
        from toksec.artifacts import write_artifact
        run=root/'.runs/run-one';repository=run/'repository';repository.mkdir(parents=True)
        source=b'int main() { return 0; }\n'
        (repository/'main.cpp').write_bytes(source)
        meta={'tag':'release/000001','candidate':'candidate-one','source_sha256':hashlib.sha256(source).hexdigest()}
        atomic_json(repository/'release.json',meta)
        def git(*args):
            return subprocess.check_output(['git','-C',str(repository),'-c','core.hooksPath=/dev/null',
                '-c','user.name=Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false',*args],stderr=subprocess.DEVNULL)
        git('init','--initial-branch=main');git('add','main.cpp','release.json');git('commit','-m','release');git('tag','release/000001')
        meta['commit']=git('rev-parse','HEAD').decode().strip()
        atomic_json(run/'manifest.json',{'level':1,'language':'cpp','started_unix':1,
            'builder_evaluation_scope':'visible_smoke_only','fingerprint':'a'*64,
            'campaign':str(root),'wall_seconds':7200,'model':'terra'})
        atomic_json(run/'state.json',{'finished':True})
        atomic_json(run/'specification.json',{'version':'v8'})
        atomic_json(root/'ledger.json',{'dollar_limit':'3'})
        (run/'launch-packet.md').write_text('Frozen inputs')
        write_artifact(run,1,'cpp')
        return run,meta

    def test_parent_grade_publishes_without_runtime_scratch(self):
        from toksec.result_storage import publish_run,read,digest
        from toksec.evaluation_artifacts import write_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,release=self.run_fixture(root);directory=run/'evaluation/grade-one'
            write_evaluation(directory,run_id=run.name,release=release,
                contract_sha256=digest(run/'artifact.json'),evaluator_sha256='a'*64,
                environment={'os':'test'},coverage='full',
                result={'checks':{'passed':True,'cases':[{'id':'bootstrap','passed':True}]}})
            (directory/'result.json').write_text('{"internal":true}')
            (directory/'candidate').mkdir();(directory/'candidate/server').write_bytes(b'executable bytes')
            (directory/'candidate/main.cpp').write_text('scratch source')
            record=publish_run(run,root/'results');published=root/'results/stage-01/cpp'
            evidence=published/'evaluation/grade-one'
            self.assertTrue((evidence/'evaluation.json').exists())
            self.assertFalse((evidence/'candidate').exists())
            self.assertFalse((evidence/'result.json').exists())
            self.assertEqual(record['run_id'],run.name)
            self.assertEqual((published/'implementation/source/main.cpp').read_bytes(),(run/'repository/main.cpp').read_bytes())
            self.assertEqual(read(evidence/'evaluation.json')['release']['commit'],release['commit'])

    def test_parent_grade_from_another_run_is_rejected(self):
        from toksec.result_storage import publish_run,digest
        from toksec.evaluation_artifacts import write_evaluation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run,release=self.run_fixture(root)
            write_evaluation(run/'evaluation/wrong-run',run_id='other-run',release=release,
                contract_sha256=digest(run/'artifact.json'),evaluator_sha256='a'*64,
                environment={},coverage='full',result=None)
            with self.assertRaisesRegex(ValueError,'does not match'):
                publish_run(run,root/'results')
            self.assertFalse((root/'results/stage-01/cpp').exists())
