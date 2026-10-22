"""Registered deterministic finite-horizon closed-loop route comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_closed_loop import audit_closed_loop


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--tag',required=True)
    args=parser.parse_args();root=args.root.resolve()
    sys.path.insert(0,str(root/'baselines/simai_runtime'))
    from make_inputs import make_inputs
    from dag_tools import ring, validate
    name='m11_closed_loop_'+args.tag
    campaign=root/'runs'/name;campaign.mkdir(exist_ok=False)
    binary=root/'m11_backend/simulation/build/scratch/ns3.36.1-LimerClosedLoopReplay-debug'
    source=Path(__file__).parent
    model=dict(period_ns=2_000_000,capacity_bps=10_000_000,
               propagation_ns=1_000_000,launch_delay_ns=3000)
    cases=[]
    for condition,bps in (('fast_B',1_000_000_000),('slow_B',100_000_000)):
        for arm in ('stay','fixed','oracle','candidate'):
            requests=[]
            if arm in ('fixed','oracle'):
                requests=[dict(version=1,request_ns=0 if arm=='fixed' else 312_000_000,
                               affected_rank=2,unavailable_rank=-1)]
            cases.append(dict(id=condition+'_'+arm,condition=condition,arm=arm,
                              alternate_bps=bps,events=[[312_000_000,2,200_000_000]],
                              requests=requests,mode='candidate' if arm=='candidate' else 'off',eligible=True))
    files=[source/'LimerClosedLoopReplay.cc',source/'ack_progress_policy_observer.h',
           source/'audit_closed_loop.py',source/'audit_dynamic_dag.py',
           source/'run_closed_loop.py',source.parent/'limer_v0/ack_progress.py',source.parent/'limer_v0/pending_route_cost.py',
           root/'baselines/simai_runtime/make_inputs.py',root/'baselines/simai_runtime/dag_tools.py']
    registration=dict(cases=cases,model=model,rounds=14,tensor_bytes_per_round=3*1024*1024,
                      source_hashes={str(p):digest(p) for p in files},binary_sha256=digest(binary),
                      library_hashes={p.name:digest(p) for p in (root/'m11_backend/simulation/build/lib').glob('*.so')},
                      claim='Observable heuristic with pending-flow execution; deterministic bounded comparison, not optimality or broad detector validation',
                      rate_model='Directed configured NIC serialization and active DCQCN pacing-cap reset; all other directions unchanged',
                      image=subprocess.check_output(['docker','--host','unix:///run/user/1005/limer-docker/docker.sock',
                        'image','inspect','--format','{{.Id}}','limer-simai-cpu:2026-10-10'],text=True).strip())
    write(campaign/'registration.json',registration);results=[]
    for case in cases:
        out=make_inputs(root,name+'/'+case['id'],4)
        topo=['10 1 0 2 8 A100','8 9']
        for plane in range(2):
            for rank in range(4):
                bps=case['alternate_bps'] if plane==1 and rank==2 else 1_000_000_000
                topo.append(f'{rank+4*plane} {8+plane} {bps}bps 500ns 0')
        (out/'topology.txt').write_text('\n'.join(topo)+'\n')
        config=[]
        for line in (out/'SimAI.conf').read_text().splitlines():
            parts=line.split()
            if parts and parts[0] in ('KMIN_MAP','KMAX_MAP','PMAX_MAP'):
                extra={'KMIN_MAP':'4','KMAX_MAP':'16','PMAX_MAP':'0.2'}[parts[0]]
                line=' '.join([parts[0],str(int(parts[1])+2),*parts[2:],'1000000000',extra,'100000000',{'KMIN_MAP':'1','KMAX_MAP':'2','PMAX_MAP':'0.2'}[parts[0]]])
            config.append(line)
        (out/'SimAI.conf').write_text('\n'.join(config)+'\n')
        flows=[]
        for iteration in range(14):
            for original in ring(4,3*1024*1024)['flows']:
                f=dict(original);offset=24*iteration
                f['id']+=offset;f['deps']=[d+offset for d in original['deps']]
                f['plane']=((original['id']-1)//4+f['src'])%2
                if iteration and original['id']<=4:
                    previous=24*(iteration-1)+20
                    f['deps']=[previous+f['src']+1,previous+(f['src']-1)%4+1]
                flows.append(f)
        graph=dict(p=4,flows=flows,mode='consecutive_network_only_ring',rounds=14)
        validate(flows,4);write(out/'graph.json',graph)
        lines=['4 336']
        for f in flows:
            lines.append(' '.join(map(str,[f['id'],f['src'],f['dst'],f['bytes'],f['plane'],len(f['deps']),*f['deps']])))
        (out/'graph.txt').write_text('\n'.join(lines)+'\n')
        controls=['1000000000 1000 1000000 '+str(len(case['requests']))]
        for request in case['requests']:
            controls.append(' '.join(map(str,[request['version'],request['request_ns'],request['affected_rank'],request['unavailable_rank']])))
        (out/'controls.txt').write_text('\n'.join(controls)+'\n')
        releases={24*iteration+rank+1:iteration*100_000_000 for iteration in range(14) for rank in range(4)}
        (out/'releases.txt').write_text(str(len(releases))+'\n'+''.join(f'{fid} {at}\n' for fid,at in releases.items()))
        m=dict(model,report_bytes=96)
        (out/'observer.txt').write_text(f'{m["period_ns"]} {m["capacity_bps"]} {m["propagation_ns"]}\n')
        (out/'rate_events.txt').write_text(str(len(case['events']))+'\n'+
                                         ''.join(' '.join(map(str,event))+'\n' for event in case['events']))
        inputs={p.name:digest(p) for p in out.iterdir() if p.name!='inputs.json'}
        write(out/'inputs.json',dict(actual_topology='four ranks, two planes, 1 Gb/s except registered rank-2 B access; runtime directed A event',
                                   case=case,model=m,hashes=inputs))
        command=['docker','--host','unix:///run/user/1005/limer-docker/docker.sock','run','--rm',
                 '--name','limer-m11-'+case['id'],'--cpus=4','--memory=4g',
                 '-e','AS_SEND_LAT=3','-e','AS_PXN_ENABLE=0','-e','AS_NVLS_ENABLE=0',
                 '-e','LD_LIBRARY_PATH=/work/m11_backend/simulation/build/lib',
                 '-v',str(root)+':/work','-w','/work/runs/'+name+'/'+case['id'],
                 'limer-simai-cpu:2026-10-10','/work/'+str(binary.relative_to(root)),
                 'topology.txt','SimAI.conf','graph.txt','trace.jsonl','controls.txt',
                 'observer.txt','rate_events.txt','progress.jsonl',case['mode'],'releases.txt']
        status=dict(id=case['id'],status='RUNNING',command=command)
        write(out/'status.json',status);start=time.monotonic()
        try:
            for path,sha in registration['source_hashes'].items():
                if digest(path)!=sha:raise ValueError('source changed after registration')
            if digest(binary)!=registration['binary_sha256']:raise ValueError('binary changed')
            for lib,sha in registration['library_hashes'].items():
                if digest(root/'m11_backend/simulation/build/lib'/lib)!=sha:raise ValueError('library changed')
            with (out/'stdout.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            status['exit_code']=result.returncode
            if result.returncode or 'drain=1' not in (out/'stdout.log').read_text():
                raise ValueError('native workload/observer did not drain')
            trace=[json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
            records=[json.loads(line) for line in (out/'progress.jsonl').read_text().splitlines()]
            audited=audit_closed_loop(graph,trace,records,m,case['mode'],case['requests'],releases)
            status.update(audited)
            alarms=status['observation']['alarms']
            localized=[e for e in alarms if e['path']==2 and e['decision_ns']>=312_000_000]
            if case['eligible']:
                first=min((e['decision_ns'] for e in localized),default=None)
                status['science']=dict(candidate_detection_scored=case['arm']=='candidate',eligible=True,delay_ms=None if first is None else (first-312_000_000)/1e6,
                                       timely=first is not None and first-312_000_000<100_000_000,
                                       miss=first is None,other_or_pre_event_alarms=[e for e in alarms if e not in localized])
            else:status['science']=dict(eligible=False,control_alarms=alarms)
            for f,sha in inputs.items():
                if digest(out/f)!=sha:raise ValueError('input changed')
            status.update(status='PASS',trace_sha256=digest(out/'trace.jsonl'),progress_sha256=digest(out/'progress.jsonl'))
        except (ValueError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
            status.update(status='FAILED',failure=str(exc))
            if isinstance(exc,subprocess.TimeoutExpired):
                subprocess.run(['docker','--host','unix:///run/user/1005/limer-docker/docker.sock','rm','-f',
                                'limer-m11-'+case['id']],capture_output=True)
        status['wall_seconds']=time.monotonic()-start
        write(out/'status.json',status);results.append(status)
        write(campaign/'summary.json',dict(registered=8,completed=len(results),results=results))
        print(case['id'],status['status'],status.get('science',{}),status.get('failure',''),flush=True)
        if status['status']!='PASS':break
    terminal=dict(registered=8,completed=len(results),complete=len(results)==8,
                  engineering_pass=all(r['status']=='PASS' for r in results))
    write(campaign/'terminal.json',terminal);print(json.dumps(terminal))


if __name__=='__main__':
    main()
