import json
import socket
import tempfile
import unittest
from pathlib import Path

from toksec import sandbox
from toksec.specification import ROOT, configuration, packet, specification, workloads


FIXTURE = r'''
use std::io::{Read,Write};
use std::net::TcpListener;
fn main() {
    assert!(!std::path::Path::new("/home/mouse9911/.codexapi").exists());
    assert!(std::env::var("OPENAI_API_KEY").is_err());
    let listener=TcpListener::bind("127.0.0.1:8080").unwrap();
    for stream in listener.incoming() {
        if let Ok(mut s)=stream {
            let mut buf=[0u8;16384];
            if s.read(&mut buf).unwrap_or(0)==0 {continue;}
            let _=s.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nhello toksec\n");
        }
    }
}
'''


class SpecificationTests(unittest.TestCase):
    def test_all_levels_publish_complete_public_contracts(self):
        for level in range(1, 6):
            spec = specification(level)
            self.assertEqual(spec['level'], level)
            self.assertEqual({w.clients for w in workloads(level)}, {256, 4096})
            self.assertTrue(spec['cases'])
            self.assertEqual(len({c['id'] for c in spec['cases']}), len(spec['cases']))
            self.assertIn('Complete wire API', packet(level))
            self.assertIn('main.rs', packet(level))
            self.assertIn('files', {c['id'] for c in spec['cases']})
        self.assertNotIn('upstreams', configuration(1))
        self.assertIn('upstreams', configuration(4))
        self.assertIn('tls_cert', configuration(5))

    def test_no_empty_or_invalid_level(self):
        for level in (0, 6):
            with self.assertRaises(ValueError):
                specification(level)

    def test_published_contracts_match_executable_suite(self):
        for level in range(1, 6):
            self.assertEqual((ROOT / f'tasks/v2/level-{level}.md').read_text(), packet(level))
            self.assertEqual(json.loads((ROOT / f'tasks/v2/level-{level}.json').read_text()), specification(level))


class RustSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.artifact = Path(cls.temporary.name) / 'candidate'
        cls.report = sandbox.build(FIXTURE, cls.artifact, 1)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_rust_compilation_and_network_namespace(self):
        self.assertTrue(self.report['passed'], self.report['diagnostics'])
        with sandbox.running(self.artifact, 1) as runtime:
            import subprocess
            command = ['nsenter', '--target', str(runtime['pid']), '--user', '--net', '--preserve-credentials',
                       '--', '/usr/bin/python3', '-c',
                       "import socket,time; time.sleep(.1); s=socket.create_connection(('127.0.0.1',8080)); s.sendall(b'GET / HTTP/1.1\\r\\n\\r\\n'); print(s.recv(1000).decode())"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('hello toksec', result.stdout)

    def test_public_suite_rejects_wrong_server(self):
        result = sandbox.invoke_driver(self.artifact, 1)
        self.assertFalse(result['passed'])
        cases = {c['id']: c for c in result['cases']}
        self.assertFalse(cases['files']['passed'])
        self.assertTrue(cases['disconnect-recovery']['passed'])

    def test_compiler_cannot_read_host_credential(self):
        source = 'const S: &str = include_str!("/home/mouse9911/.codexapi"); fn main(){println!("{}", S);}'
        report = sandbox.build(source, Path(self.temporary.name) / 'bad', 1)
        self.assertFalse(report['passed'])
        self.assertFalse((Path(self.temporary.name) / 'bad/server').exists())

    def test_rust_unit_tests_run_in_sandbox(self):
        candidate = Path(self.temporary.name) / 'tests'
        report = sandbox.build('#[test] fn isolated(){assert!(!std::path::Path::new("/home/mouse9911/.codexapi").exists());}', candidate, 1, test=True)
        self.assertTrue(report['passed'], report['diagnostics'])
        self.assertTrue(sandbox.self_test(candidate)['passed'])

    def test_level_five_approved_crypto_and_compression_libraries_link(self):
        candidate = Path(self.temporary.name) / 'libraries'
        source = '''extern "C" { fn OpenSSL_version_num() -> u64; fn zlibVersion() -> *const u8; }
#[test] fn libraries(){unsafe{assert!(OpenSSL_version_num()>0); assert!(!zlibVersion().is_null());}}'''
        report = sandbox.build(source, candidate, 5, test=True)
        self.assertTrue(report['passed'], report['diagnostics'])
        self.assertTrue(sandbox.self_test(candidate)['passed'])
