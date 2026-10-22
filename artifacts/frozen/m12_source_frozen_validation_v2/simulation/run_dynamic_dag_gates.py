"""Prospectively registered scripted execution gates, not detector efficacy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from audit_dynamic_dag import audit_dynamic


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def cases():
    def request(version=1,at=5000,rank=2,unavailable=-1):
        return dict(version=version,request_ns=at,affected_rank=rank,unavailable_rank=unavailable)
    model=dict(capacity_bps=1_000_000_000,propagation_ns=1000,timeout_ns=1_000_000)
    rows=[dict(id='ring_no_control',requests=[],changed=0,activations=0),
          dict(id='ring_pending_switch',requests=[request()],changed=2,activations=1),
          dict(id='ring_slow_control',requests=[request()],changed=0,activations=1,
               model=dict(model,propagation_ns=250_000)),
          dict(id='ring_missing_ready',requests=[request(unavailable=2)],changed=0,activations=0),
          dict(id='ring_two_versions',requests=[request(),request(2,80000,1)],
               changed_min=3,activations=2),
          dict(id='reject_nonconsecutive_version',requests=[request(2)],expected_exit=3),
          dict(id='same_source_chain',requests=[request(rank=0)],micro='sender',
               changed=1,activations=1),
          dict(id='destination_chain',requests=[request(rank=1)],micro='receiver',
               changed=1,activations=1),
          dict(id='unequal_join',requests=[request(rank=0)],micro='join',
               changed=1,activations=1)]
    for row in rows:row.setdefault('model',dict(model));row.setdefault('expected_exit',0)
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--tag',required=True);args=parser.parse_args();root=args.root.resolve()
    sys.path.insert(0,str(root/'baselines/simai_runtime'))
    from make_inputs import make_inputs
    from dag_tools import ring
    name='m9_execution_'+args.tag;campaign=root/'runs'/name;campaign.mkdir(exist_ok=False)
    binary=root/'m9_backend/simulation/build/scratch/ns3.36.1-LimerDynamicDagReplay-debug'
    libraries={p.name:digest(p) for p in (root/'m9_backend/simulation/build/lib').glob('*.so')}
    image=subprocess.check_output(['docker','--host','unix:///run/user/1005/limer-docker/docker.sock',
        'image','inspect','--format','{{.Id}}','limer-simai-cpu:2026-10-10'],text=True).strip()
    hashes=dict(binary=digest(binary),cpp=digest(Path(__file__).with_name('LimerDynamicDagReplay.cc')),
                runner=digest(__file__),auditor=digest(Path(__file__).with_name('audit_dynamic_dag.py')),
                input_builder=digest(root/'baselines/simai_runtime/make_inputs.py'),
                graph_builder=digest(root/'baselines/simai_runtime/dag_tools.py'))
    registration=dict(cases=cases(),hashes=hashes,library_hashes=libraries,image=image,
        claim='Scripted dynamic pending-flow execution only; no detected fault or adaptive policy measurement')
    write(campaign/'registration.json',registration);results=[]
    for case in registration['cases']:
        out=make_inputs(root,name+'/'+case['id'],4)
        topo=['10 1 0 2 8 A100','8 9']
        for plane in range(2):
            for rank in range(4):topo.append(f'{rank+4*plane} {8+plane} 200Gbps 500ns 0')
        (out/'topology.txt').write_text('\n'.join(topo)+'\n')
        graph=ring(4,3*1024*1024)
        for f in graph['flows']:f['plane']=((f['id']-1)//4+f['src'])%2
        if 'micro' in case:
            f1=dict(id=1,src=0,dst=1,bytes=1024*1024,plane=0,deps=[])
            if case['micro']=='sender':
                flows=[f1,dict(id=2,src=0,dst=2,bytes=1000,plane=0,deps=[1])]
            elif case['micro']=='receiver':
                flows=[f1,dict(id=2,src=1,dst=2,bytes=20,plane=0,deps=[1])]
            else:
                flows=[f1,dict(id=2,src=0,dst=2,bytes=1000,plane=0,deps=[1]),
                       dict(id=3,src=1,dst=2,bytes=20,plane=0,deps=[1]),
                       dict(id=4,src=2,dst=3,bytes=10000,plane=0,deps=[2,3])]
            graph=dict(p=4,flows=flows,mode='execution_micrograph')
        write(out/'graph.json',graph)
        lines=[f'4 {len(graph["flows"])}']
        for f in graph['flows']:
            lines.append(' '.join(map(str,[f['id'],f['src'],f['dst'],f['bytes'],f['plane'],len(f['deps']),*f['deps']])))
        (out/'graph.txt').write_text('\n'.join(lines)+'\n')
        m=case['model'];lines=[f'{m["capacity_bps"]} {m["propagation_ns"]} {m["timeout_ns"]} {len(case["requests"])}']
        for r in case['requests']:
            lines.append(' '.join(map(str,[r['version'],r['request_ns'],r['affected_rank'],r['unavailable_rank']])))
        (out/'controls.txt').write_text('\n'.join(lines)+'\n')
        inputs={f:digest(out/f) for f in ('graph.json','graph.txt','controls.txt','topology.txt','SimAI.conf')}
        write(out/'frozen_inputs.json',inputs)
        command=['docker','--host','unix:///run/user/1005/limer-docker/docker.sock','run','--rm',
                 '--name','limer-m9-'+case['id'],'--cpus=4','--memory=4g',
                 '-e','AS_SEND_LAT=3','-e','AS_PXN_ENABLE=0','-e','AS_NVLS_ENABLE=0',
                 '-e','LD_LIBRARY_PATH=/work/m9_backend/simulation/build/lib',
                 '-v',str(root)+':/work','-w','/work/runs/'+name+'/'+case['id'],
                 'limer-simai-cpu:2026-10-10','/work/'+str(binary.relative_to(root)),
                 'topology.txt','SimAI.conf','graph.txt','trace.jsonl','controls.txt']
        status=dict(id=case['id'],status='RUNNING',expected_exit=case['expected_exit'],command=command)
        write(out/'status.json',status);start=time.monotonic()
        try:
            if digest(binary)!=hashes['binary']:raise ValueError('binary changed after registration')
            for lib,sha in libraries.items():
                if digest(root/'m9_backend/simulation/build/lib'/lib)!=sha:raise ValueError('library changed')
            with (out/'stdout.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            status['exit_code']=result.returncode
            if result.returncode!=case['expected_exit']:raise ValueError('unexpected process result')
            text=(out/'stdout.log').read_text()
            if case['expected_exit']:
                if 'Nonconsecutive/stale route version' not in text:raise ValueError('wrong expected rejection')
                status['claim']='Expected invalid-input rejection, not a completed workload'
            else:
                if 'drain=1' not in text:raise ValueError('backend maps did not drain')
                records=[json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
                check=audit_dynamic(graph,records,case['requests'],m)
                if check['activated_versions']!=case['activations']:raise ValueError('wrong activation count')
                if 'changed' in case and check['changed_flows']!=case['changed']:raise ValueError('wrong changed-flow count')
                if 'changed_min' in case and check['changed_flows']<case['changed_min']:raise ValueError('insufficient pending cutover')
                status['audit']=check;status['trace_sha256']=digest(out/'trace.jsonl')
            for f,sha in inputs.items():
                if digest(out/f)!=sha:raise ValueError('input changed during execution')
            status['status']='PASS'
        except (ValueError,subprocess.TimeoutExpired,FileNotFoundError) as exc:
            status.update(status='FAILED',failure=str(exc))
            if isinstance(exc,subprocess.TimeoutExpired):
                subprocess.run(['docker','--host','unix:///run/user/1005/limer-docker/docker.sock','rm','-f',
                                'limer-m9-'+case['id']],capture_output=True)
        status['wall_seconds']=time.monotonic()-start
        write(out/'status.json',status);results.append(status)
        print(case['id'],status['status'],status.get('audit',{}),status.get('failure',''),flush=True)
        write(campaign/'summary.json',dict(registered=len(registration['cases']),completed=len(results),results=results))
        if status['status']!='PASS':break
    terminal=dict(complete=len(results)==len(registration['cases']),passed=all(r['status']=='PASS' for r in results),
                  registered=len(registration['cases']),completed=len(results))
    write(campaign/'terminal.json',terminal);print(json.dumps(terminal))


if __name__=='__main__':main()
