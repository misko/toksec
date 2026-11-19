import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(set(range(24)) <= os.sched_getaffinity(0), 'requires 24 CPU coordination host')
class CoordinationTests(unittest.TestCase):
    def test_handoff_preserves_workers_and_starts_queued_jobs_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'toksec').mkdir(); (root / 'toksec/__init__.py').write_text('')
            worker = '''import json,sys,time,os
from pathlib import Path
run=Path(sys.argv[sys.argv.index('--run')+1])
p=run/'manifest.json'; m=json.loads(p.read_text())
if m['started_unix'] is not None: raise RuntimeError('duplicate launch')
m['started_unix']=time.time();p.write_text(json.dumps(m))
(run/'worker-pid').write_text(str(os.getpid()))
time.sleep(3)
(run/'done').write_text('completed')
'''
            (root / 'toksec/__main__.py').write_text(worker)
            (root / 'scripts').mkdir()
            (root / 'scripts/run_parallel.py').write_text('''import json,sys
from pathlib import Path
p=Path(sys.argv[sys.argv.index('--directory')+1])/'batch.json'
b=json.loads(p.read_text());b['status']='complete'
for j in b['jobs']:j['status']='complete'
p.write_text(json.dumps(b))
''')
            supervisor = root / 'supervisor.py'
            supervisor.write_text('''import sys,time,subprocess,json,os,fcntl
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--directory')+1]);p=root/'batch.json'
b=json.loads(p.read_text());lock=(root/'batch.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
j=b['jobs'][0]
worker=subprocess.Popen([sys.executable,'-m','toksec','run','--run',j['run']],start_new_session=True)
j.update(status='running',pid=worker.pid);b['pid']=os.getpid();p.write_text(json.dumps(b))
while True:time.sleep(1)
''')
            supervisors=[]; directories=[]
            try:
                for index, cpus in enumerate((list(range(6)),list(range(18,24)))):
                    directory=root/f'batch-{index}';directory.mkdir();directories.append(directory)
                    jobs=[]
                    for n in range(2):
                        run=directory/f'run-{n}';run.mkdir()
                        (run/'manifest.json').write_text(json.dumps({'started_unix':None,'cpu_affinity':cpus}))
                        jobs.append({'id':f'{index}-{n}','run':str(run),'stage':1,'cpus':cpus,'status':'prepared'})
                    (directory/'batch.json').write_text(json.dumps({'status':'running','jobs':jobs}))
                    supervisors.append(subprocess.Popen([sys.executable,str(supervisor),'run','--directory',str(directory)],cwd=root))
                deadline=time.monotonic()+5
                while any('pid' not in json.loads((d/'batch.json').read_text()) for d in directories):
                    if time.monotonic()>deadline:self.fail('supervisor startup timeout')
                    time.sleep(.05)
                old_pids=[json.loads((d/'batch.json').read_text())['jobs'][0]['pid'] for d in directories]
                done=subprocess.run([sys.executable,str(ROOT/'scripts/coordinate_batches.py'),
                    '--batch',str(directories[0]),'--batch',str(directories[1]),
                    '--state',str(root/'coordination.json'),'--key-file',str(root/'unused'),
                    '--results',str(root/'results'),'--parallel','3'],capture_output=True,text=True,timeout=20)
                self.assertEqual(done.returncode,0,done.stderr)
                for i,directory in enumerate(directories):
                    batch=json.loads((directory/'batch.json').read_text())
                    self.assertEqual(batch['status'],'complete')
                    self.assertEqual(int((directory/'run-0/worker-pid').read_text()),old_pids[i])
                    self.assertTrue((directory/'run-0/done').exists())
                    self.assertTrue((directory/'run-1/done').exists())
                    self.assertTrue((directory/'run-1/manifest.before-coordination.json').exists())
            finally:
                for p in supervisors:
                    if p.poll() is None:p.kill()
                    p.wait()
