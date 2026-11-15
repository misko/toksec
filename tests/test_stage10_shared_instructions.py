import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stage10 import runner
from toksec.stages import module as stage_module
ROOT = stage_module(10, 'packet').ROOT
STAGE = stage_module(10, 'packet').STAGE
input_files = stage_module(10, 'packet').input_files
packet = stage_module(10, 'packet').packet


class Stage10SharedInstructionTests(unittest.TestCase):
    def test_packet_uses_shared_policy_once_and_marks_partial_coverage(self):
        shared = (ROOT / 'RULES.md').read_text()
        artifacts = (ROOT / 'stages/common/ARTIFACTS.md').read_text()
        for language in ('cpp', 'rust'):
            with self.subTest(language=language):
                prompt = packet(language, '0.15')
                self.assertEqual(prompt.count(shared), 1)
                self.assertEqual(prompt.count(artifacts), 1)
                self.assertIn('strict $0.15 model-spend cap', prompt)
                self.assertIn('coverage is partial', prompt)
                self.assertIn('performance measurements are provisional diagnostics', prompt)
                self.assertIn('No starter code', prompt)
                self.assertNotIn((STAGE / 'builder/RULES.md').read_text(), prompt)
                self.assertNotIn((STAGE / 'preview' / (language + '-launch-packet.md')).read_text(), prompt)

    def test_input_allowlist_has_only_selected_language_and_shared_rules(self):
        for language, other in [('cpp', 'rust'), ('rust', 'cpp')]:
            files = input_files(language)
            self.assertEqual(files['builder/RULES.md'], ROOT / 'RULES.md')
            self.assertIn('builder/languages/' + language + '.md', files)
            self.assertNotIn('builder/languages/' + other + '.md', files)
            self.assertFalse(any('host/' in name or 'preview/' in name for name in files))

    def test_prepare_files_prompt_and_inventory_use_same_shared_policy(self):
        for language in ('cpp', 'rust'):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'run'
                with patch.object(runner.subprocess, 'check_output', return_value='toolchain fixture'):
                    runner.prepare(destination, language=language, budget='0.15')
                manifest = json.loads((destination / 'manifest.json').read_text())
                copied = destination / 'builder-inputs/builder/RULES.md'
                self.assertEqual(copied.read_bytes(), (ROOT / 'RULES.md').read_bytes())
                self.assertEqual(manifest['input_sha256']['builder/RULES.md'],
                                 hashlib.sha256(copied.read_bytes()).hexdigest())
                self.assertEqual((destination / 'launch-packet.md').read_text(), packet(language, '0.15'))
                self.assertEqual(manifest['api_coverage'], 'partial')
                self.assertEqual(manifest['performance_scope'], 'provisional')
                self.assertFalse((destination / 'builder-inputs/host').exists())
                self.assertFalse((destination / 'builder-inputs/preview').exists())

    def test_current_policy_changes_invalidate_stage10_identity(self):
        before = runner.identity()
        original = Path.read_bytes

        def changed(path):
            body = original(path)
            return body + b'\nchanged shared policy\n' if path == ROOT / 'RULES.md' else body

        with patch.object(Path, 'read_bytes', changed):
            self.assertNotEqual(before, runner.identity())

    def test_invalid_language_budget_or_wall_limit_creates_no_run(self):
        for options in ({'language': 'python'}, {'budget': '3'}, {'budget': '0'},
                        {'wall_seconds': 1}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'run'
                with self.assertRaises(ValueError):
                    runner.prepare(destination, **options)
                self.assertFalse(destination.exists())
