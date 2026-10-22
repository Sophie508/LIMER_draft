"""M7 development/validation injector controls; never detector inputs."""
import json,subprocess,time
from limer_v0 import orchestrator as o
args=o.parse_args(None)
config=json.loads(args.config.read_text())
kind=config.get('m7_control','nominal')
original_build=o.build_topology
original_round=o._run_collective_round

def root_run(command):
 return subprocess.run(command,check=True,capture_output=True,text=True)

def build(*a,**kw):
 d=original_build(*a,**kw)
 try:
  features=[]
  for fabric,endpoints in d.fabrics.items():
   for rank,e in endpoints.items():
    for name,run in [(e.host_interface,d._host_command_runner(rank)),(e.switch_interface,root_run)]:
     run(['ethtool','-K',name,'tso','off','gso','off','gro','off'])
     after=run(['ethtool','-k',name]).stdout
     assert all(f+': off' in after for f in ['tcp-segmentation-offload','generic-segmentation-offload','generic-receive-offload'])
     features.append(dict(interface=name,after=after))
  ifbs={}
  for fabric,endpoints in d.fabrics.items():
   for rank,e in endpoints.items():
    name=f'ifbm7{fabric}{rank}';ifbs[(fabric,rank)]=name
    existing=json.loads(d._host_command_runner(rank)(['tc','-j','qdisc','show','dev',e.host_interface]).stdout)
    if any(q['kind']!='noqueue' for q in existing):d._host_command_runner(rank)(['tc','qdisc','del','dev',e.host_interface,'root'])
    root_run(['ip','link','add',name,'type','ifb']);root_run(['ip','link','set',name,'up'])
    root_run(['ethtool','-K',name,'tso','off','gso','off','gro','off'])
    root_run(['tc','qdisc','add','dev',e.switch_interface,'handle','ffff:','ingress'])
    root_run(['tc','filter','add','dev',e.switch_interface,'parent','ffff:','protocol','all','matchall','action','mirred','egress','redirect','dev',name])
    root_run(['tc','qdisc','replace','dev',name,'root','netem','limit','10000','delay','1ms','rate','100mbit','loss','0%'])
  folder=args.results_dir/args.run_id
  (folder/'diagnostic_features.json').write_text(json.dumps(features,indent=2)+'\n')
  original_apply=d.apply_fault_profile
  def apply(profile,route='A',rank=2):
   start=time.monotonic_ns()
   injector=ifbs[(route,rank)]
   command=['tc','qdisc','replace','dev',injector,'root','netem','limit','10000','loss',str(profile.loss_pct)+'%','rate',str(profile.rate_mbit)+'mbit']
   if not kind.startswith('reorder'):command+=['delay',str(profile.delay_ms)+'ms']
   record=dict(interface=injector,rank=rank,route=route,profile=dict(rate_mbit=profile.rate_mbit,delay_ms=profile.delay_ms,loss_pct=profile.loss_pct))
   if kind.startswith('reorder'):
    delay='40ms' if kind=='reorder40' else '10ms'
    command+=['delay',delay,'reorder','25%','50%']
   root_run(command)
   record.update(t_before_ns=start,t_after_ns=time.monotonic_ns(),diagnostic_loss_pct=profile.loss_pct,diagnostic_injector=injector,diagnostic_loss_command=command,diagnostic_placement='sA-eth3 ingress after sender segmentation',m7_control=kind)
   return record
  d.apply_fault_profile=apply
  background=[]
  if kind=='congestion':
   destination=d.fabrics['B'][3].local_ip
   background.append(d.hosts[3].popen(['python3','/runtime/udp_control.py','receive',destination,str(folder/'background_receiver.json')]))
   time.sleep(.1)
   background.append(d.hosts[2].popen(['python3','/runtime/udp_control.py','send',destination,str(folder/'background_sender.json')]))
  original_stop=d.stop
  def stop():
   (folder/'all_switch_final_qdiscs.json').write_text(json.dumps({e.switch_interface:json.loads(root_run(['tc','-s','-j','qdisc','show','dev',e.switch_interface]).stdout) for ends in d.fabrics.values() for e in ends.values()},indent=2)+'\n')
   (folder/'all_ingress_final_qdiscs.json').write_text(json.dumps({name:json.loads(root_run(['tc','-s','-j','qdisc','show','dev',name]).stdout) for name in ifbs.values()},indent=2)+'\n')
   for proc in background:
    if proc.poll() is None:proc.terminate()
   for proc in background:
    proc.wait(timeout=5)
   original_stop()
  d.stop=stop
  return d
 except BaseException:
  d.stop();raise

def round(*a,**kw):
 if kind=='pause':
  start=time.monotonic_ns();time.sleep(.25)
  a[4].emit('CONTROL_ROUND_PAUSE',start_ns=start,end_ns=time.monotonic_ns())
 return original_round(*a,**kw)

o.build_topology=build;o._run_collective_round=round
summary=o.execute_run(config,args.results_dir,args.workdir,args.run_id)
print(json.dumps(summary))
raise SystemExit(0 if summary.get('status')=='complete' else 1)
