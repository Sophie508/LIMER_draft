"""Static path calibration; no controller timing or LIMER efficacy claim."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import time
from dag_tools import ring, verify_trace
from make_inputs import make_inputs
from run_replay import DOCKER, ROOT

BINARY='/work/baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-LimerDualPlaneReplay-debug'


def inputs(name,a_bw,b_bw,switch):
    p=4
    graph=ring(p,3*1024*1024)
    for f in graph['flows']:
        f['initial_plane']=((f['id']-1)//p+f['src'])%2
        f['plane']=1 if switch and f['src']==p-1 and f['initial_plane']==0 else f['initial_plane']
    graph.update(route_policy='static_localized_switch' if switch else 'stay',fault_rank=p-1)
    out=make_inputs(ROOT,name,p)
    topo=[f'{2*p+2} 1 0 2 {2*p} A100',f'{2*p} {2*p+1}']
    for plane in range(2):
        for rank in range(p):
            bandwidth=(a_bw if plane==0 else b_bw) if rank==p-1 else 200
            topo.append(f'{rank+p*plane} {2*p+plane} {bandwidth}Gbps 500ns 0')
    (out/'topology.txt').write_text('\n'.join(topo)+'\n')
    text=[f'{p} {len(graph["flows"])}']
    for f in graph['flows']:
        text.append(' '.join(map(str,[f['id'],f['src'],f['dst'],f['bytes'],f['plane'],len(f['deps']),*f['deps']])))
    (out/'graph.txt').write_text('\n'.join(text)+'\n')
    (out/'graph.json').write_text(json.dumps(graph,indent=2)+'\n')
    config=[]
    additions={'KMIN_MAP':[(40_000_000_000,160),(20_000_000_000,80)],
               'KMAX_MAP':[(40_000_000_000,640),(20_000_000_000,320)],
               'PMAX_MAP':[(40_000_000_000,.2),(20_000_000_000,.2)]}
    for line in (out/'SimAI.conf').read_text().splitlines():
        words=line.split()
        if words and words[0] in additions:
            words[1]=str(int(words[1])+2)
            for pair in additions[words[0]]:words.extend(map(str,pair))
            line=' '.join(words)
        config.append(line)
    (out/'SimAI.conf').write_text('\n'.join(config)+'\n')
    payload=defaultdict(int)
    for f in graph['flows']:payload[f['plane']]+=f['bytes']
    manifest=json.loads((out/'inputs.json').read_text())
    manifest.update(logical_ranks=p,physical_network_endpoints=2*p,GPUs_per_server='not a physical GPU model',
                    switches=2,endpoint_representation='two network endpoint placeholders per logical rank',
                    fault_rank=p-1,last_A_Gbps=a_bw,last_B_Gbps=b_bw,route_policy=graph['route_policy'],
                    added_ECN_rows=additions,
                    plane_payload_bytes=dict(payload),detection_coordination_cost_modeled=False)
    for f in ('topology.txt','graph.txt','graph.json','SimAI.conf'):
        manifest['hashes'][f]=hashlib.sha256((out/f).read_bytes()).hexdigest()
    (out/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return out,graph


def run(name,a,b,switch):
    out,graph=inputs(name,a,b,switch)
    command=DOCKER+['run','--rm','--name','limer-'+name,'--cpus=4','--memory=8g',
                   '-e','AS_SEND_LAT=3','-e','AS_PXN_ENABLE=0','-e','AS_NVLS_ENABLE=0',
                   '-v',str(ROOT)+':/work','-w','/work/runs/'+name,'limer-simai-cpu:2026-10-10',
                   BINARY,'topology.txt','SimAI.conf','graph.txt','trace.jsonl']
    status={'name':name,'command':command,'start_unix':time.time(),
            'binary_sha256':hashlib.sha256((ROOT/BINARY.removeprefix('/work/')).read_bytes()).hexdigest()}
    with (out/'stdout.log').open('w') as log:
        try:status['exit_code']=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120).returncode
        except subprocess.TimeoutExpired:
            status.update(exit_code=None,timeout=True)
            subprocess.run(DOCKER+['rm','-f','limer-'+name],capture_output=True)
    status['wall_seconds']=time.time()-status['start_unix']
    try:
        if status['exit_code']!=0:raise ValueError('Process failed')
        status['trace_check']=verify_trace(graph,out/'trace.jsonl')
        index={f['id']:f for f in graph['flows']}
        for line in (out/'trace.jsonl').read_text().splitlines():
            e=json.loads(line);f=index[e['id']];p=graph['p']
            if (e['plane'],e['port_src'],e['port_dst'])!=(f['plane'],f['src']+p*f['plane'],f['dst']+p*f['plane']):
                raise ValueError('Wrong physical endpoint/plane')
        summary=out.joinpath('stdout.log').read_text()
        if 'drain=1' not in summary:raise ValueError('Transport maps did not drain')
        # The topology is disconnected across planes. Matching peer endpoints
        # and complete delivery require a same-plane physical path.
        if sum(f['bytes'] for f in graph['flows'])!=2*(graph['p']-1)*graph['N']:
            raise ValueError('Payload accounting failed')
        status['status']='PASS'
    except (ValueError,FileNotFoundError) as e:status.update(status='FAILED',failure=str(e))
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(name,status['status'],status.get('trace_check',{}).get('makespan_ns'),flush=True)
    return status


