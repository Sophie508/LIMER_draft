"""Run registered replay cases on the dedicated scratch Docker daemon."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from dag_tools import save_graph, verify_trace
from make_inputs import make_inputs

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
DOCKER=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock']
BINARY='/work/baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-LimerDagReplay-debug'


def run_case(name, graph, slowdown=1, mtu=9000):
    out=make_inputs(ROOT,name,graph['p'],slowdown,mtu)
    graph_hash=save_graph(graph,out)
    command=DOCKER+['run','--rm','--name','limer-'+name,'--cpus=4','--memory=8g',
                   '-e','AS_SEND_LAT=3','-e','AS_PXN_ENABLE=0','-e','AS_NVLS_ENABLE=0',
                   '-v',str(ROOT)+':/work','-w','/work/runs/'+name,
                   'limer-simai-cpu:2026-10-10',BINARY,'topology.txt','SimAI.conf',
                   'graph.txt','trace.jsonl']
    status=dict(command=command,graph_sha256=graph_hash,start_unix=time.time(),
                binary_sha256=hashlib.sha256((ROOT/BINARY.removeprefix('/work/')).read_bytes()).hexdigest())
    with (out/'stdout.log').open('w') as log:
        try:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            status['exit_code']=process.returncode
        except subprocess.TimeoutExpired:
            status['exit_code']=None
            status['timeout']=True
            subprocess.run(DOCKER+['rm','-f','limer-'+name],capture_output=True)
    status['wall_seconds']=time.time()-status['start_unix']
    try:
        if status['exit_code'] != 0:
            raise ValueError('Process did not succeed')
        status['trace_check']=verify_trace(graph,out/'trace.jsonl')
        status['status']='PASS'
        # For the one-flow transport gate, verify the sender did not finish after
        # only a prefix. This is a payload-only lower bound; headers add latency.
        if len(graph['flows'])==1:
            f=graph['flows'][0]
            events={e['event']:e['ns'] for e in map(json.loads,(out/'trace.jsonl').read_text().splitlines())}
            bw=200/slowdown if f['src']==graph['p']-1 else 200
            minimum=3000+f['bytes']*8/bw
            status['minimum_serialization_ns']=minimum
            if events['send']-events['start'] < minimum:
                raise ValueError('Premature whole-flow send completion')
    except (ValueError,FileNotFoundError) as error:
        status['status']='FAILED'
        status['failure']=str(error)
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(name,status['status'],status.get('trace_check',{}).get('makespan_ns'),flush=True)
    return status


def transport(prefix):
    results=[]
    for mtu in (9000,1000):
        for size in (20,8999,9000,9001,17999,18000,18001):
            graph=dict(p=2,mode='transport_gate',flows=[dict(id=1,src=0,dst=1,bytes=size,deps=[])])
            results.append(run_case(f'{prefix}_mtu{mtu}_b{size}',graph,mtu=mtu))
    (ROOT/'logs'/f'{prefix}_summary.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport-prefix')
    args=parser.parse_args()
    if args.transport_prefix:
        transport(args.transport_prefix)
