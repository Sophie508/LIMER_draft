"""Execute preregistered gates, then a fixed matched comparison matrix."""
import argparse
import json
from pathlib import Path
import subprocess
from dag_tools import convert_optcc, ring, validate
from run_replay import ROOT, run_case


def generate_optcc(p,k,n,loss):
    output=ROOT/'baselines/optcc_generated'/f'p{p}_k{k}_N{n}_L{loss}'
    if output.exists():
        if 'Validation: PASS' not in (output/'stdout.log').read_text():
            raise RuntimeError('Existing generator artifact did not pass')
        return convert_optcc(json.loads((output/'dag.json').read_text()),n)
    output.mkdir(parents=True,exist_ok=False)
    binary=ROOT/'baselines/optcc_linux/single_straggler'
    with (output/'stdout.log').open('w') as log:
        subprocess.run([str(binary),str(p),str(k),str(n),'1000',str(loss)],
                       cwd=output,stdout=log,stderr=subprocess.STDOUT,check=True)
    if 'Validation: PASS' not in (output/'stdout.log').read_text():
        raise RuntimeError('Generator validation failed')
    return convert_optcc(json.loads((output/'dag.json').read_text()),n)


def gates():
    specifications=[
        ('mixed',3,[(1,0,1,18001,[]),(2,0,2,9000,[1]),(3,1,2,20,[1]),
                    (4,2,0,8999,[2,3]),(5,0,1,20001,[1,4]),(6,0,1,1001,[5])]),
        ('same_peer_roots',2,[(1,0,1,20,[]),(2,0,1,18001,[])]),
        ('control_chain',2,[(1,0,1,20,[]),(2,1,0,20,[1]),(3,0,1,20,[1,2])])]
    results=[]
    for name,p,rows in specifications:
        flows=[dict(id=i,src=s,dst=d,bytes=b,deps=deps) for i,s,d,b,deps in rows]
        validate(flows,p)
        results.append(run_case('serial_scheduler_'+name,dict(p=p,mode='scheduler_gate',flows=flows)))
    golden=json.loads((ROOT/'baselines/optcc_checks/single_L2/dag.json').read_text())
    results.append(run_case('serial_optcc_smoke_p5_L2',convert_optcc(golden,1048576),slowdown=2))
    results.append(run_case('serial_ring_smoke_p5_L2',ring(5,5*1048576),slowdown=2))
    results.append(run_case('serial_optcc_bubble_p5_L1',generate_optcc(5,4,5*1048576,1)))
    (ROOT/'logs/serial_replay_gates_summary.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(r['status']!='PASS' for r in results):
        raise RuntimeError('A required gate failed; performance matrix remains unrun')


def measurements():
    gates=json.loads((ROOT/'logs/serial_replay_gates_summary.json').read_text())
    transport=json.loads((ROOT/'logs/serial_repaired_summary.json').read_text())
    if any(r['status']!='PASS' for r in gates+transport):
        raise RuntimeError('Required gate has not passed')
    results=[]
    for p,mib in [(5,5),(5,20),(16,15),(16,60)]:
        n=mib*1048576
        graphs={'ring':ring(p,n),'optcc':generate_optcc(p,4,n,2)}
        for repeat in (1,2,3):
            for arm in ('ring','optcc'):
                name=f'compare_p{p}_N{mib}MiB_{arm}_r{repeat}'
                results.append(run_case(name,graphs[arm],slowdown=2))
        results.append(run_case(f'healthy_p{p}_N{mib}MiB_ring',graphs['ring']))
    for k in (8,16):
        graph=generate_optcc(16,k,15*1048576,2)
        results.append(run_case(f'sensitivity_p16_N15MiB_optcc_k{k}',graph,slowdown=2))
    (ROOT/'logs/measurements_summary.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['gates','measurements'])
    args=parser.parse_args()
    if args.phase=='gates':
        gates()
    else:
        measurements()
