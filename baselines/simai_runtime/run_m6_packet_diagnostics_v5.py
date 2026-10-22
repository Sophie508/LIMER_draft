"""Eight preregistered observation-only runs; no hidden replacements."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,subprocess,time
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
SOURCE=ROOT/'limer_source_guarded_v1'
D=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock']
IMAGE='limer-mininet-diagnostic:2026-10-10'
while not (ROOT/'logs/m6_packet_diagnostic_v4_summary.json').exists():time.sleep(1)
folder=SOURCE/'configs/m6_packet_diagnostic_v5';folder.mkdir(exist_ok=False)
tasks=[]
for mode in ['disabled']:
 for loss in [0,.5,1,2]:
  config=json.loads((SOURCE/'configs/m5_retrans_observation/l1.json').read_text())
  config.update(fault_loss_pct=loss,diagnostic_offload_mode=mode,
       what_changes=f'Exploratory captures and {mode} segmentation settings; no new trigger.',
       expected='Observe packet granularity, sequence evidence, observer latency and capture cost; no efficacy guarantee.')
  handle=str(loss).replace('.','p');name=f'm6_packet_v5_{mode}_l{handle}'
  f=folder/f'{mode}_l{handle}.json';f.write_text(json.dumps(config,indent=2)+'\n')
  tasks.append((name,str(f.relative_to(SOURCE))))
(ROOT/'logs/m6_packet_diagnostic_v5_registration.json').write_text(json.dumps(tasks,indent=2)+'\n')

def run(task):
 name,config=task
 command=D+['run','--rm','--name','limer-'+name,'--privileged','--cpus=4','--memory=4g',
  '-v',str(SOURCE)+':/work','-v',str(ROOT/'baselines/simai_runtime')+':/runtime',
  '-v',str(ROOT/'mininet_results')+':/results',IMAGE,'bash','/runtime/mininet_entry.sh',
  'python3','/runtime/m6_packet_diagnostic_wrapper_v5.py','--config',config,
  '--results-dir','/results','--workdir','/work','--run-id',name]
 record=dict(name=name,config=config,command=command,start_unix=time.time(),
  image_id=subprocess.check_output(D+['image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip(),
  hashes={s:hashlib.sha256((SOURCE/s).read_bytes()).hexdigest() for s in
    [config,'limer_v0/worker.py','limer_v0/orchestrator.py','limer_v0/tcp_retrans.py']},
  wrapper_sha256=hashlib.sha256((ROOT/'baselines/simai_runtime/m6_packet_diagnostic_wrapper_v5.py').read_bytes()).hexdigest())
 status=ROOT/'logs'/f'{name}.status.json';status.write_text(json.dumps(record,indent=2)+'\n')
 with (ROOT/'logs'/f'{name}.log').open('w') as out:
  try:record['exit_code']=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,timeout=1800).returncode
  except subprocess.TimeoutExpired:
   record.update(timeout=True,exit_code=None);subprocess.run(D+['rm','-f','limer-'+name],capture_output=True)
 record['wall_seconds']=time.time()-record['start_unix']
 for f in ['summary.json','correctness.json']:
  p=ROOT/'mininet_results'/name/f
  if p.exists():record[f[:-5]]=json.loads(p.read_text())
 status.write_text(json.dumps(record,indent=2)+'\n');print(name,record.get('exit_code'),record.get('summary',{}).get('status'),flush=True)
 return record
first=run(tasks[0])
if first['exit_code']!=0:
 results=[first]
 (ROOT/'logs/m6_packet_diagnostic_v5_expansion_blocked.json').write_text(json.dumps(dict(reason='initial capture pilot failed',unrun=tasks[1:]),indent=2)+'\n')
else:
 with ThreadPoolExecutor(max_workers=2) as pool:results=[first]+list(pool.map(run,tasks[1:]))
(ROOT/'logs/m6_packet_diagnostic_v5_summary.json').write_text(json.dumps(results,indent=2)+'\n')
