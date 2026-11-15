import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toksec.storage import atomic_json
from toksec import evaluate
from toksec.specification import fingerprint, workloads

class RecoveryTests(unittest.TestCase):
    def test_resume_preserves_completed_workloads_and_never_rebuilds(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'main.cpp'; source.write_text('int main(){}')
            first=workloads(3)[0].id
            saved={'framework':fingerprint(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                   'level':3,'language':'cpp','checks':{'passed':True,'cases':[{'passed':True}]},
                   'benchmarks':{first:{'retained':True}}}
            atomic_json(root/'result.json',saved)
            def load(*args,**kwargs):
                return {kwargs['workload']:{'eligible':True,'failures':0}}
            with patch('toksec.evaluate.sandbox.invoke_driver',side_effect=load) as driver, patch('toksec.evaluate.sandbox.build') as build:
                result=evaluate.resume(source,root,3,'cpp')
            build.assert_not_called()
            self.assertEqual(driver.call_count,len(workloads(3))-1)
            self.assertEqual(result['benchmarks'][first],{'retained':True})
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'does not match'):
                evaluate.resume(source,root,3,'cpp')

    def test_resume_never_bypasses_api_gate(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'main.cpp'; source.write_text('int main(){}')
            atomic_json(root/'result.json',{'framework':fingerprint(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'level':5,'language':'cpp','checks':{'passed':False}})
            with patch('toksec.evaluate.sandbox.invoke_driver') as load:
                with self.assertRaisesRegex(ValueError,'API gate'):
                    evaluate.resume(source,root,5,'cpp')
                load.assert_not_called()
