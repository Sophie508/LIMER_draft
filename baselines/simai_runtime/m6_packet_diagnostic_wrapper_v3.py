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
        (folder/'diagnostic_features.json').write_text(json.dumps(features,indent=2)+'\n')
        pair=clock();(folder/'capture_clock_start.json').write_text(json.dumps(pair)+'\n')
        for side,interface,popen in [('sender','w2-eth0',d.hosts[2].popen),('switch','sA-eth3',subprocess.Popen)]:
            err=(folder/f'{side}_capture.stderr').open('w');handles.append(err)
            command=['python3','/runtime/m6_capture_metadata.py',interface,
                     str(folder/side),str(folder/'capture.stop')]
            proc=popen(command,stdout=subprocess.DEVNULL,stderr=err);processes.append(proc)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('capture startup failed:'+str(command))
                if (folder/f'{side}.ready').exists():break
                time.sleep(.02)
            else:raise RuntimeError('capture did not report readiness')
    except BaseException:
        for proc in processes:
            if proc.poll() is None:proc.send_signal(signal.SIGINT);proc.wait(timeout=3)
        for handle in handles:handle.close()
        d.stop();raise
    original_stop=d.stop
    def stop():
        (folder/'capture.stop').write_text('stop\n')
        (folder/'capture_clock_end.json').write_text(json.dumps(clock())+'\n')
        qdisc=d._host_command_runner(2)(['tc','-s','-j','qdisc','show','dev','w2-eth0']).stdout
        (folder/'injector_final_qdisc.json').write_text(qdisc+'\n')
        for proc in processes:
            proc.wait(timeout=5)
            if proc.returncode!=0:raise RuntimeError('metadata capture failed')
        for handle in handles:handle.close()
        original_stop()
    d.stop=stop
    return d

o.build_topology=build
summary=o.execute_run(config,args.results_dir,args.workdir,args.run_id)
print(json.dumps(summary,indent=2))
raise SystemExit(0 if summary.get('status')=='complete' else 1)
