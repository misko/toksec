import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from toksec.specification import ROOT

spec=importlib.util.spec_from_file_location('evaluation_cli',ROOT/'evaluate.py')
cli=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class EvaluationCliTests(unittest.TestCase):
    def test_exit_codes_distinguish_api_failures_and_invalid_measurements(self):
        for section,result,expected in [
            ('api',{'checks':{'passed':False}},2),
            ('api',{'checks':{'passed':True}},0),
            ('performance',{'checks':{'passed':True},'benchmarks':{}},3),
            ('performance',{'checks':{'passed':True},'benchmarks':{'a':{'eligible':False,'failures':0}}},3),
            ('performance',{'checks':{'passed':True},'benchmarks':{'a':{'eligible':True,'failures':0}}},0)]:
            with self.subTest(section=section,result=result),tempfile.TemporaryDirectory() as tmp:
                with patch.object(cli.evaluate,'evaluate',return_value=result),redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['--section',section,'--level','1','--output',tmp]),expected)
