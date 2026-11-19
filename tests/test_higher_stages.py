import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from toksec import campaign, controller, context, releases, sandbox
from toksec.specification import ROOT, packet, specification, workloads
from stages.common.smoke.api import cases


class HigherStagesTests(unittest.TestCase):
    def test_profiles_and_disclosure(self):
        for level in range(1, 6):
            for language in ('rust', 'cpp'):
                spec = specification(level, language)
                text = packet(level, language)
                self.assertFalse(spec['profile']['starter'])
                self.assertEqual(len(cases(level)), 1 if level == 1 else 3 if level == 2 else 4)
                self.assertEqual(text.count('# Shared builder rules'), 1)
                for case in spec['cases']:
                    if case['id'] != 'bootstrap':
                        self.assertNotIn('`'+case['id']+'`', text)
                self.assertNotIn('full_acceptance', text)
        self.assertNotIn('tls_listen', specification(5)['configuration'])
        self.assertFalse(any(w.tls or w.gzip for w in workloads(5)))
        self.assertTrue(any(w.host == 'beta.test' for w in workloads(3)))
        self.assertTrue(any(w.id.startswith('cache-hit') for w in workloads(5)))

    def test_minimal_fixtures_all_stages(self):
        from toksec.fixtures import create_smoke
        for level in range(1, 6):
            with tempfile.TemporaryDirectory() as tmp:
                create_smoke(tmp, level)
                paths = {p.name for p in Path(tmp).rglob('*')}
                self.assertFalse(paths & {'secret', 'escape', 'inside-link', 'pipe', 'stall', 'key.pem'})
                if level >= 3:
                    self.assertEqual((Path(tmp)/'www/beta/hello.txt').read_bytes(), b'beta toksec\n')

    def test_all_builder_paths_use_smoke_and_tagged_sources(self):
        # Real preparation, build, Git publication and checkpoint; mock protocol
        # execution so this verifies isolation, not server conformance.
        for level in (3, 4, 5):
            with self.subTest(level=level), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                campaign.initialize(root/'campaign', '3')
                with self.assertRaisesRegex(ValueError, 'without starter'):
                    controller.prepare(root/'campaign', level, starter='anything')
                run = Path(controller.prepare(root/'campaign', level, language='cpp')['run'])
                report = {'passed': True, 'cases': [{'id': c.id, 'passed': True} for c in cases(level)]}
                def smoke_only(*args, **kwargs):
                    self.assertTrue(kwargs.get('smoke'))
                    return report
                with patch('toksec.sandbox.evaluate', side_effect=smoke_only):
                    submitted = controller.submit(run, 'int main(){return 0;}')
                    self.assertTrue(submitted['checks']['passed'])
                    controller.revalidate(run, 'latest')
                    first = releases.initialize(run)
                    controller.submit(run, 'int main(){return 0;} // second milestone')
                    last = releases.publish(run, 'Second test milestone')
                    self.assertNotEqual(first['tag'], last['tag'])
                    checkpoint = context.checkpoint(run, packet(level, 'cpp'))
                self.assertEqual(last['evaluation_scope'], 'visible_smoke_only')
                for hidden in ('routing-interactions', 'proxy-fragmented-upload', 'cache-byte-limit'):
                    self.assertNotIn(hidden, json.dumps(checkpoint))
                (run/'repository/main.cpp').write_text('broken untagged source')
                with patch('toksec.evaluate.sandbox.evaluate', return_value={'passed': False, 'cases': [{'id':'held-out', 'passed':False}]}), patch('toksec.evaluate.sandbox.invoke_driver') as load:
                    grade = releases.grade(run, root/'grade', performance=True)
                load.assert_not_called()
                self.assertEqual(grade['release']['tag'], last['tag'])
                self.assertTrue(grade['build']['passed'])
                self.assertEqual(grade['grading']['performance_credit'], 0)

    def test_unknown_scoped_workload_rejected(self):
        # Invalid selectors must not invoke a load process or silently measure all.
        with tempfile.TemporaryDirectory() as tmp:
            campaign.initialize(Path(tmp)/'c', '3')
            run = Path(controller.prepare(Path(tmp)/'c', 3, language='cpp')['run'])
            report = {'passed': True, 'cases': [{'id': c.id, 'passed': True} for c in cases(3)]}
            with patch('toksec.sandbox.evaluate', return_value=report):
                controller.submit(run, 'int main(){}')
            with patch('toksec.sandbox.invoke_driver') as driver:
                with self.assertRaisesRegex(ValueError, 'unknown workload'):
                    controller.measure(run, 'nonexistent')
                driver.assert_not_called()

    def test_real_higher_stage_smoke_with_ordinary_upstreams(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact=Path(tmp)/'candidate'
            source=(ROOT/'tests/fixtures/smoke_server.rs').read_text()
            report=sandbox.build(source,artifact,5)
            self.assertTrue(report['passed'],report)
            for level in (3,4,5):
                with self.subTest(level=level):
                    result=sandbox.evaluate(artifact,level,smoke=True)
                    self.assertTrue(result['passed'],result)
                    self.assertEqual(len(result['cases']),4)

    def test_catalog_contract_references_exist_and_do_not_duplicate_ids(self):
        from stages.common.grading.catalog import catalog
        for level in range(1,6):
            rows=catalog(level)
            self.assertEqual(len({(r['visibility'],r['id']) for r in rows}),len(rows))
            self.assertTrue(all((ROOT/r['contract']).is_file() for r in rows))

    def test_rust_cannot_explicitly_link_crypto_in_stage5(self):
        with tempfile.TemporaryDirectory() as tmp:
            source='#[link(name="crypto")] extern "C" { fn OpenSSL_version_num() -> u64; } fn main(){unsafe{println!("{}", OpenSSL_version_num());}}'
            result=sandbox.build(source,Path(tmp)/'bad',5)
            self.assertFalse(result['passed'])


    def test_proxy_benchmark_reserves_and_measures_upstream_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact=Path(tmp)/'candidate'
            self.assertTrue(sandbox.build((ROOT/'tests/fixtures/smoke_server.rs').read_text(),artifact,4)['passed'])
            result=sandbox.invoke_driver(artifact,4,'benchmark',workload='proxy-4096-256',rounds=1)
            metrics=result['proxy-4096-256']['rounds'][0]
            self.assertNotEqual(metrics['upstream_cpu'],metrics['server_cpu'])
            self.assertNotIn(metrics['upstream_cpu'],metrics['generator_cpus'])
            self.assertTrue(metrics['upstream_sample_valid'])
            self.assertGreater(metrics['successes'],0)
            self.assertGreaterEqual(metrics['upstream_utilization'],0)
