"""Register explicit paired throughput development conditions before execution."""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from limerlab.config import Scenario
from limerlab.paths import ROOT,sha,tree_hashes,write_json
from limerlab.runner import resolve_build
from integration_campaign import execute


def plan(preset):
    cases=[]
    def add(family,completion,helper,seed=111210016,policy='always',method='G11'):
        scene=Scenario(family=family,rounds=1,chunks_per_phase=512,
            horizon_ns=(400 if preset=='pilot' else 2000)*1000000,fault_ns=40000000,
            seed=seed,detector='service',policy=policy,replacement_lifetime='phase',
            phases_per_round=4 if preset=='pilot' else 30,
            relay_completion=completion,helper_mode=helper)
        name='{}-{}-{}-{}-{}-s{}'.format(family,method,completion,helper,policy,seed)
        cases.append(dict(name=name,method=method,scene=scene.dictionary()))
    if preset=='pilot':
        for family in ('blackhole','healthy','weak_loss'):
            for completion,helper in (('final_ack','idle'),('pipelined','idle'),('pipelined','shared')):
                add(family,completion,helper)
        for family in ('quarter','delay','no_idle_helpers'):
            add(family,'pipelined','shared')
    else:
        for family in ('healthy','blackhole','weak_loss'):
            add(family,'pipelined','shared')
        add('blackhole','pipelined','idle')
        for family in ('healthy','blackhole','weak_loss'):
            add(family,'pipelined','shared',seed=111212001)
    return dict(schema='limer-throughput-development-v1',preset=preset,cases=cases,
        registered_unix=time.time(),run_count=len(cases),
        role='Paired development and one fresh matched seed, not a population guarantee',
        changes='Separate relay physical release from logical confirmation; explicit charged shared-helper lending extension',
        expectation='Idle-only release may improve throughput but remains late. Shared helpers may recover 70-80% while all physical contention and final ACKs remain charged.',
        denominator='Healthy useful payload divided by whole-job time for the same workload and seed. Also compare immutable 480.178448-ms healthy reference.',
        target_retention=[0.70,0.80],all_failed_attempts_retained=True)


def register(build,out,preset):
    out=Path(out);record,_,_=resolve_build(build);out.mkdir(parents=True,exist_ok=False)
    p=plan(preset);p.update(build=str(Path(build).resolve()),build_sha256=sha(Path(build)/'build.json'),
        binary_sha256=record['binary_sha256'],source_hashes={d:tree_hashes(ROOT/d) for d in ('src','python','tools')})
    write_json(out/'registration.json',p)
    print('Registered {} cases: {}'.format(len(p['cases']),out))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','register','execute'])
    p.add_argument('--preset',choices=['pilot','full'],default='pilot');p.add_argument('--build',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    if not 1<=a.workers<=2:p.error('Use at most two concurrent raw runs within the research quota')
    if a.action=='plan':write_json(a.out,plan(a.preset))
    elif a.action=='register':register(a.build,a.out,a.preset)
    else:execute(a.out,a.workers,'all')
