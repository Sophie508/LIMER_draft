"""Registered M7 v1 development ledger, first nominal infrastructure gate."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,subprocess,time
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
SOURCE=ROOT/'limer_source_m7_tcp_v1'
D=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock']
IMAGE='limer-mininet-diagnostic:2026-10-10'
folder=SOURCE/'configs/m7_development_ingress_v3';folder.mkdir(exist_ok=False)
tasks=[]
for label,loss,control in [('nominal',0,'nominal'),('loss1',1,'nominal'),('congestion',0,'congestion'),('reorder10',0,'reorder10')]:
 config=json.loads((SOURCE/'configs/m5_retrans_observation/l1.json').read_text())
 config.update(fault_loss_pct=loss,tcp_retrans_interval_s=0,tcp_delivery_interval_s=.005,tcp_loss_detector=True,post_fault_rounds=4,m7_control=control,
  what_changes='Prospective tcp-loss-v1 host decision; segmented ingress IFB recipe; recovery off.',expected='Test persistent loss confirmation and DSACK/reorder veto; preserve misses and false alarms.')
 f=folder/(label+'.json');f.write_text(json.dumps(config,indent=2)+'\n')
 tasks.append(('m7_dev_ingress_v3_'+label,str(f.relative_to(SOURCE))))
(ROOT/'logs/m7_development_ingress_v3_registration.json').write_text(json.dumps(tasks,indent=2)+'\n')

def run(task):
 name,config=task
 cmd=D+['run','--rm','--name','limer-'+name,'--privileged','--cpus=4','--memory=4g','-v',str(SOURCE)+':/work','-v',str(ROOT/'baselines/simai_runtime')+':/runtime','-v',str(ROOT/'mininet_results')+':/results',IMAGE,'bash','/runtime/mininet_entry.sh','python3','/runtime/m7_tcp_wrapper_ingress_v3.py','--config',config,'--results-dir','/results','--workdir','/work','--run-id',name]
 record=dict(name=name,config=config,command=cmd,start_unix=time.time(),image_id=subprocess.check_output(D+['image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip(),hashes={s:hashlib.sha256((SOURCE/s).read_bytes()).hexdigest() for s in [config,'limer_v0/worker.py','limer_v0/orchestrator.py','limer_v0/tcp_loss.py']},wrapper_sha256=hashlib.sha256((ROOT/'baselines/simai_runtime/m7_tcp_wrapper_ingress_v3.py').read_bytes()).hexdigest(),randomness='uncontrolled kernel netem draws; independent unpaired lifecycles')
 status=ROOT/'logs'/(name+'.status.json');status.write_text(json.dumps(record,indent=2)+'\n')
 with (ROOT/'logs'/(name+'.log')).open('w') as out:
  try:record['exit_code']=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,timeout=600).returncode
  except subprocess.TimeoutExpired:
   record.update(timeout=True,exit_code=None);subprocess.run(D+['rm','-f','limer-'+name],capture_output=True)
 record['wall_seconds']=time.time()-record['start_unix']
 for item in ['summary','correctness']:
  f=ROOT/'mininet_results'/name/(item+'.json')
  if f.exists():record[item]=json.loads(f.read_text())
 status.write_text(json.dumps(record,indent=2)+'\n');print(name,record.get('exit_code'),record.get('summary',{}).get('status'),flush=True)
 return record
first=run(tasks[0])
if first['exit_code']!=0:
 results=[first];(ROOT/'logs/m7_development_ingress_v3_blocked.json').write_text(json.dumps(dict(unrun=tasks[1:],reason='nominal infrastructure gate failed')))
else:
 with ThreadPoolExecutor(max_workers=2) as pool:results=[first]+list(pool.map(run,tasks[1:]))
(ROOT/'logs/m7_development_ingress_v3_summary.json').write_text(json.dumps(results,indent=2)+'\n')
