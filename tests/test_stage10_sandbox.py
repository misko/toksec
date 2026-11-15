import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from stage10 import sandbox


class PolicyTests(unittest.TestCase):
    def test_ssl_only_extension(self):
        with patch.object(subprocess, 'check_output', side_effect=[
                ' (NEEDED) Shared library: [libssl.so.3]\n (NEEDED) Shared library: [libcrypto.so.3]', '']):
            self.assertIsNone(sandbox.inspect_binary('unused'))
        with patch.object(subprocess, 'check_output', return_value=' (NEEDED) Shared library: [libcurl.so.4]'):
            self.assertIn('libcurl', sandbox.inspect_binary('unused'))

    def test_fail_closed_kernel_limits(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, value in {'memory.max': str(sandbox.MEMORY), 'memory.swap.max': '0',
                                'pids.max': '4', 'cpu.max': '100000 100000'}.items():
                (root / name).write_text(value)
            # Absolute path remains absolute when joined, for a local synthetic cgroup.
            with patch.object(sandbox, 'Path', side_effect=lambda p: root if p == '/sys/fs/cgroup' else Path(p)):
                self.assertEqual(sandbox._verify_cgroup('', sandbox.MEMORY, 4), root)
                (root / 'memory.max').write_text('max')
                with self.assertRaises(RuntimeError):
                    sandbox._verify_cgroup('', sandbox.MEMORY, 4)

    def test_invalid_workers(self):
        for workers in (0, 5, True):
            with self.assertRaises(ValueError):
                with sandbox.running('/absent', '/absent', workers=workers):
                    pass


@unittest.skipUnless(os.environ.get('TOKSEC_STAGE10_SANDBOX_TEST') == '1',
                     'explicit integration opt-in: starts benign contained processes')
class IntegrationTests(unittest.TestCase):
    def test_build_runtime_limits_mounts_network_cleanup(self):
        source = r'''
#include <openssl/ssl.h>
#include <sys/resource.h>
#include <unistd.h>
#include <cstdio>
#include <fstream>
int main(){
  if(!OPENSSL_init_ssl(0,nullptr)) return 1;
  rlimit r; getrlimit(RLIMIT_NOFILE,&r);
  std::printf("fd=%lu\n",r.rlim_cur); std::fflush(stdout);
  if(access("/etc/ssh",F_OK)==0 || access("/home",F_OK)==0) return 2;
  std::ofstream f("/tmp/probe"); f << "scratch"; f.close();
  if(!f) return 3;
  if(access("/fixtures/config/nginx.conf",R_OK)!=0) return 4;
  sleep(30);
}
'''
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = sandbox.build(source, root / 'artifact', 'cpp')
            self.assertTrue(report['passed'], report)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            (fixtures / 'config').mkdir()
            (fixtures / 'config' / 'nginx.conf').write_text('workers=2\n')
            (fixtures / 'www').mkdir()
            (fixtures / 'tls').mkdir()
            with sandbox.running(root / 'artifact', fixtures, timeout=35) as runtime:
                pid, cgroup = runtime['pid'], runtime['cgroup']
                self.assertNotEqual(os.readlink(f'/proc/{pid}/ns/net'), os.readlink('/proc/self/ns/net'))
                self.assertEqual((cgroup / 'pids.max').read_text().strip(), '4')
                self.assertEqual((cgroup / 'memory.max').read_text().strip(), str(sandbox.MEMORY))
                for _ in range(100):
                    if 'fd=4096' in runtime['log'].read_text():
                        break
                    time.sleep(.01)
                self.assertIn('fd=4096', runtime['log'].read_text())
            self.assertFalse(Path(f'/proc/{pid}').exists())
            self.assertFalse(cgroup.exists())

    def test_rust_build_selftest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = sandbox.build('fn main(){assert_eq!(2+2,4);}', root / 'artifact', 'rust', test=True)
            self.assertTrue(report['passed'], report)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            (fixtures / 'config').mkdir()
            (fixtures / 'config' / 'nginx.conf').write_text('workers=2\n')
            (fixtures / 'www').mkdir()
            (fixtures / 'tls').mkdir()
            result = sandbox.self_test(root / 'artifact', fixtures)
            self.assertTrue(result['passed'], result)

@unittest.skipUnless(os.environ.get('TOKSEC_STAGE10_SANDBOX_TEST') == '1', 'explicit integration opt-in')
class AggregateIntegrationTests(unittest.TestCase):
    def test_scratch_is_charged_and_daemon_cleanup(self):
        script = """import os,time
if os.fork() == 0:
 os.setsid()
 with open('/tmp/scratch','wb') as f: f.write(b'x' * (32*1024*1024))
 time.sleep(30)
else:
 time.sleep(30)
"""
        with tempfile.TemporaryFile() as log:
            with sandbox._unit(sandbox._base()+['--remount-ro','/','--','/usr/bin/python3','-c',script],
                               log, tasks=4, timeout=35) as runtime:
                cgroup = runtime['cgroup']
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    memory = int((cgroup/'memory.current').read_text())
                    if memory >= 32*1024*1024:
                        break
                    time.sleep(.02)
                self.assertGreaterEqual(memory, 32*1024*1024)
                pids = (cgroup/'cgroup.procs').read_text().split()
                self.assertEqual(len(pids), 3)
            self.assertTrue(all(not Path('/proc/'+p).exists() for p in pids))

    def test_tree_memory_limit(self):
        script = """import os,time
for _ in range(2):
 if os.fork() == 0:
  a=bytearray(300*1024*1024)
  time.sleep(20)
  os._exit(0)
time.sleep(20)
"""
        with tempfile.TemporaryFile() as log:
            with sandbox._unit(sandbox._base()+['--','/usr/bin/python3','-c',script],
                               log, tasks=4, timeout=25) as runtime:
                cgroup = runtime['cgroup']
                deadline = time.monotonic()+10
                killed = 0
                while time.monotonic() < deadline:
                    events = dict(line.split() for line in (cgroup/'memory.events').read_text().splitlines())
                    killed = int(events['oom_kill'])
                    if killed:
                        break
                    time.sleep(.05)
                self.assertGreater(killed, 0, 'combined children must trigger the tree memory limit')
                self.assertLessEqual(int((cgroup/'memory.peak').read_text()), sandbox.MEMORY)


if __name__ == '__main__':
    unittest.main()
