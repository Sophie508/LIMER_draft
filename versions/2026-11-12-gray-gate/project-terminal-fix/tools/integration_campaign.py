"""Freeze and run the declared phase-integration development comparison."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from limerlab.config import Scenario
from limerlab.paths import ROOT,sha,tree_hashes,write_json,read_json
from limerlab.runner import resolve_build,run_case


def plan():
    cases=[]
    def add(name,method,family='blackhole',chunks=512,lifetime='phase',policy='benefit',phases=4,horizon=400,seed=111200000):
        scene=Scenario(family=family,rounds=1,chunks_per_phase=chunks,
            horizon_ns=horizon*1000000,fault_ns=40000000,node=0,seed=seed,
            detector='service',policy=policy,replacement_lifetime=lifetime,phases_per_round=phases)
        cases.append(dict(name=name,method=method,scene=scene.dictionary()))
    for chunks in (64,512):
        for lifetime in ('persistent','phase'):
            add('pilot-c{}-{}'.format(chunks,lifetime),'G11',chunks=chunks,lifetime=lifetime,phases=30 if chunks==64 else 4)
    methods=[('G00','always'),('G10','always'),('G01','always'),('G11','always'),('G11','benefit'),('A_ONLY','always')]
    for family in ('healthy','blackhole','quarter','weak_loss','delay'):
        for method,policy in methods:
            add('matrix-{}-{}-{}'.format(family,method,policy),method,family=family,policy=policy)
    for method,policy,family in [('G11','benefit','healthy'),('A_ONLY','always','blackhole'),('G11','always','blackhole'),('G11','benefit','blackhole')]:
        add('full-ring-{}-{}-{}'.format(family,method,policy),method,family=family,policy=policy,phases=30,horizon=2000,seed=111210016)
    return dict(schema='limer-phase-integration-development-v1',cases=cases,
        role='Development integration and paired ablations, not independent 95% acceptance',
        changes='Phase-local binding/gate lifetime and explicit A_ONLY business control; detector rules unchanged',
        expectation='AB eligibility returns at every phase; long cohorts may expose fresh B-prime work; short cohorts may not. Gate benefit is conditional.',
        deadline_ns=100000000,run_count=len(cases),native_default_phases_per_round=30,
        development_phases_per_round=4,original_release_commit='501a0f50f51fd90c9ea9d3582b08e17fee4590ab')


def register(build,out):
    out=Path(out);record,_,_=resolve_build(build)
    out.mkdir(parents=True,exist_ok=False)
    p=plan();p.update(build=str(Path(build).resolve()),build_sha256=sha(Path(build)/'build.json'),
        binary_sha256=record['binary_sha256'],source_hashes={d:tree_hashes(ROOT/d) for d in ('src','python','tools')})
    write_json(out/'registration.json',p)
    return p


def execute(out,workers,selection):
    out=Path(out);p=read_json(out/'registration.json')
    if sha(Path(p['build'])/'build.json')!=p['build_sha256']:raise ValueError('Registered build changed')
    for d,hashes in p['source_hashes'].items():
        if tree_hashes(ROOT/d)!=hashes:raise ValueError('Registered source changed: '+d)
    cases=[c for c in p['cases'] if selection=='all' or c['name'].startswith(selection)]
    cases=[c for c in cases if not (out/'attempts'/(c['name']+'.json')).exists()]
    (out/'attempts').mkdir(exist_ok=True)
    def run(c):
        started=time.time();attempt=dict(name=c['name'],started_unix=started)
        try:
            r=run_case(p['build'],out/'runs'/c['name'],c['method'],Scenario(**c['scene']),
                archive_to=out/'archives'/(c['name']+'.tar.gz'),keep_raw=False)
            attempt.update(valid=True,result=r)
        except Exception as e:attempt.update(valid=False,error=repr(e))
        attempt['elapsed_seconds']=time.time()-started
        write_json(out/'attempts'/(c['name']+'.json'),attempt)
        print(json.dumps(dict(name=c['name'],valid=attempt['valid'],elapsed=round(attempt['elapsed_seconds'],2),
            **({k:attempt['result']['performance'].get(k) for k in ('communication_ms','new_Bprime_completions','new_Bprime_phases','fresh_Bprime_payload_bytes')} if attempt['valid'] else dict(error=attempt['error'])))),flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run,c) for c in cases]):future.result()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','register','execute'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path);p.add_argument('--workers',type=int,default=2)
    p.add_argument('--selection',choices=['all','pilot','matrix','full-ring'],default='all');a=p.parse_args()
    if a.action=='plan':write_json(a.out,plan())
    elif a.action=='register':register(a.build,a.out)
    else:
        if not 1<=a.workers<=4:p.error('workers must be 1..4')
        execute(a.out,a.workers,a.selection)
