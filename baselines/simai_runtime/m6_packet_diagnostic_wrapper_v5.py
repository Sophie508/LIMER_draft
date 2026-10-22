"""Exploratory packet/offload metadata, never a detection or recovery input."""
import json,signal,subprocess,time
from pathlib import Path
from limer_v0 import orchestrator as o
args=o.parse_args(None)
config=json.loads(args.config.read_text())
folder=args.results_dir/args.run_id
original_build=o.build_topology

def clock():
    start=time.monotonic_ns();realtime=time.time_ns();end=time.monotonic_ns()
    return dict(monotonic_before_ns=start,realtime_ns=realtime,monotonic_after_ns=end)

def build(*a,**kw):
    d=original_build(*a,**kw)
    features=[];processes=[];handles=[]
    try:
        for fabric,endpoints in d.fabrics.items():
            for rank,e in endpoints.items():
                for side,name,run in [('host',e.host_interface,d._host_command_runner(rank)),('switch',e.switch_interface,lambda cmd:subprocess.run(cmd,check=True,capture_output=True,text=True))]:
                    before=run(['ethtool','-k',name]).stdout
                    if config['diagnostic_offload_mode']=='disabled':run(['ethtool','-K',name,'tso','off','gso','off','gro','off'])
                    after=run(['ethtool','-k',name]).stdout
                    if config['diagnostic_offload_mode']=='disabled':
                        for feature in ['tcp-segmentation-offload','generic-segmentation-offload','generic-receive-offload']:
                            assert feature+': off' in after,(name,feature,after)
                    features.append(dict(fabric=fabric,rank=rank,side=side,interface=name,before=before,after=after))
        def root_run(command):
            return subprocess.run(command,check=True,capture_output=True,text=True)
        root_run(['ip','link','add','ifbm6','type','ifb'])
        root_run(['ip','link','set','ifbm6','up'])
        root_run(['ethtool','-K','ifbm6','tso','off','gso','off','gro','off'])
        root_run(['tc','qdisc','add','dev','sA-eth3','handle','ffff:','ingress'])
        root_run(['tc','filter','add','dev','sA-eth3','parent','ffff:','protocol','all',
                  'matchall','action','mirred','egress','redirect','dev','ifbm6'])
        root_run(['tc','qdisc','replace','dev','ifbm6','root','netem','limit','10000','loss','0%'])
        original_apply=d.apply_fault_profile
        def apply(profile,route='A',rank=2):
            start=time.monotonic_ns()
            record=original_apply(o.TcProfile(rate_mbit=profile.rate_mbit,delay_ms=profile.delay_ms,loss_pct=0),route,rank)
            command=['tc','qdisc','replace','dev','ifbm6','root','netem','limit','10000','loss',str(profile.loss_pct)+'%']
            root_run(command)
            record.update(t_before_ns=start,t_after_ns=time.monotonic_ns(),
                          diagnostic_loss_pct=profile.loss_pct,diagnostic_injector='ifbm6',diagnostic_loss_command=command,
                          diagnostic_placement='sA-eth3 ingress after sender segmentation')
            return record
        d.apply_fault_profile=apply
        (folder/'diagnostic_features.json').write_text(json.dumps(features,indent=2)+'\n')
        pair=clock();(folder/'capture_clock_start.json').write_text(json.dumps(pair)+'\n')
        for side,interface,popen in [('sender','w2-eth0',d.hosts[2].popen),('receiver','w3-eth0',d.hosts[3].popen),('ifb','ifbm6',subprocess.Popen)]:
            err=(folder/f'{side}_capture.stderr').open('w');handles.append(err)
            command=['tcpdump','-Z','root','-nn','-U','-G','8','-W','1','-s','128','-i',interface,'-w',str(folder/f'{side}.pcap'),
                     'tcp and host 10.0.0.3 and host 10.0.0.4 and port 15000']
            proc=popen(command,stdout=subprocess.DEVNULL,stderr=err);processes.append(proc)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('capture startup failed:'+str(command))
                if 'listening on' in (folder/f'{side}_capture.stderr').read_text():break
                time.sleep(.02)
            else:raise RuntimeError('capture did not report readiness')
    except BaseException:
        for proc in processes:
            if proc.poll() is None:proc.send_signal(signal.SIGINT);proc.wait(timeout=3)
        for handle in handles:handle.close()
        d.stop();raise
    original_stop=d.stop
    def stop():
        (folder/'capture_clock_end.json').write_text(json.dumps(clock())+'\n')
        qdisc=root_run(['tc','-s','-j','qdisc','show','dev','ifbm6']).stdout
        (folder/'injector_final_qdisc.json').write_text(qdisc+'\n')
        for proc in processes:
            proc.wait(timeout=5)
            if proc.returncode!=0:raise RuntimeError('timed capture failed')
        for handle in handles:handle.close()
        original_stop()
    d.stop=stop
    return d

o.build_topology=build
summary=o.execute_run(config,args.results_dir,args.workdir,args.run_id)
print(json.dumps(summary,indent=2))
raise SystemExit(0 if summary.get('status')=='complete' else 1)
