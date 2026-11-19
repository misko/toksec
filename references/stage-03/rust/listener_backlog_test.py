"""Inspect the kernel's listening queue limit without generating request traffic."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from toksec import sandbox

PROBE = '''import json, subprocess, time
end=time.monotonic()+2
while True:
 p=subprocess.run(['/usr/bin/ss','-lnt'],capture_output=True,text=True,check=True)
 rows=[line for line in p.stdout.splitlines() if '127.0.0.1:8080' in line]
 if rows:
  fields=rows[0].split()
  print(json.dumps({'ss_output':p.stdout,'backlog':int(fields[2])}))
  break
 if time.monotonic()>end: raise RuntimeError('listener not ready')
 time.sleep(.01)
'''

def main():
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=False)
    records=[]
    for argument in sys.argv[2:]:
        artifact=Path(argument).resolve()
        with sandbox.running(artifact,3,smoke=True) as runtime:
            p=subprocess.run(['nsenter','--target',str(runtime['pid']),'--user','--net','--preserve-credentials','--','/usr/bin/python3','-c',PROBE],capture_output=True,text=True,check=True,timeout=5)
            record=json.loads(p.stdout)
            record.update(artifact=str(artifact),source_sha256=hashlib.sha256((artifact/'main.rs').read_bytes()).hexdigest())
            records.append(record)
    result={'method':'kernel ss -lnt inspection; no request traffic','records':records,'passed':records[0]['backlog']==128 and records[1]['backlog']>=4096}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__': main()
