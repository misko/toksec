import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_current_code_does_not_import_pilot_modules(self):
        forbidden = {'legacy', 'controller', 'runner', 'metering', 'capacity', 'evaluator', 'probe'}
        paths = [ROOT / 'evaluate.py']
        for directory in ('toksec', 'stages', 'evaluation', 'scripts'):
            paths.extend((ROOT / directory).rglob('*.py'))
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split('.')[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported = [(node.module or '').split('.')[0]]
                else:
                    continue
                self.assertFalse(forbidden.intersection(imported), str(path))
        subprocess.run([sys.executable, '-c',
                        'import sys; import toksec.runner; import toksec.execution.counted; '
                        'assert not any(k == "legacy" or k.startswith("legacy.") for k in sys.modules)'],
                       cwd=ROOT, check=True, capture_output=True, timeout=15)

    def test_old_root_modules_and_ambiguous_input_locations_are_gone(self):
        for name in ('capacity.py', 'controller.py', 'evaluator.py', 'metering.py',
                     'probe.py', 'runner.py', 'stage10', 'prompts', 'experiments', 'starters', 'proposals'):
            self.assertFalse((ROOT / name).exists(), name)
        self.assertTrue((ROOT / 'tests/fixtures/implementations/static.rs').is_file())
        self.assertTrue((ROOT / 'legacy/python_pilot/tasks/http/level-1.md').is_file())

    def test_relocated_stage10_inputs_match_frozen_inventory(self):
        packet = ROOT / 'stages/stage-10'
        manifest = json.loads((packet / 'input-manifest.json').read_text())
        for entry in manifest['entries']:
            source = packet / entry['path']
            body = source.read_bytes()
            self.assertEqual(len(body), entry['bytes'], entry['path'])
            self.assertEqual(hashlib.sha256(body).hexdigest(), entry['sha256'], entry['path'])

    def test_stage10_definition_changes_do_not_change_stage1_fingerprint(self):
        from toksec.specification import fingerprint
        from toksec.specification import counted_fingerprint as identity
        before_stage1, before_stage10 = fingerprint(), identity()
        original = Path.read_bytes
        target = ROOT / 'stages/stage-10/builder/HTTP.md'

        def changed(path):
            value = original(path)
            return value + b'\nchanged stage10 input\n' if path == target else value

        with patch.object(Path, 'read_bytes', changed):
            self.assertEqual(fingerprint(), before_stage1)
            self.assertNotEqual(identity(), before_stage10)
